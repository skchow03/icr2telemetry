import win32gui, win32process, pymem
import ctypes, ctypes.wintypes
import struct, time, sys, os

# Constants for memory state
MEM_COMMIT = 0x1000
PAGE_READABLE = (0x04 | 0x02 | 0x20 | 0x40)  # Read/write/execute-readable states

# MEMORY_BASIC_INFORMATION structure used by VirtualQueryEx
class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', ctypes.wintypes.LPVOID),
        ('AllocationBase', ctypes.wintypes.LPVOID),
        ('AllocationProtect', ctypes.wintypes.DWORD),
        ('RegionSize', ctypes.c_size_t),
        ('State', ctypes.wintypes.DWORD),
        ('Protect', ctypes.wintypes.DWORD),
        ('Type', ctypes.wintypes.DWORD)
    ]

# Finds the process ID by matching visible window title against all keywords
def find_pid_by_window_title(keywords):
    result = {'pid': None, 'title': None}

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if all(k.lower() in title.lower() for k in keywords):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                result['pid'] = pid
                result['title'] = title
                raise StopIteration  # Exit early if match found
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except StopIteration:
        pass

    return result if result['pid'] else None

# Scans the memory of the process for a specific byte signature
def find_pattern_address(pm, pattern_bytes):
    mbi = MEMORY_BASIC_INFORMATION()
    addr = 0
    max_addr = 0x7FFFFFFF  # 2 GB for 32-bit space

    while addr < max_addr:
        if ctypes.windll.kernel32.VirtualQueryEx(
            pm.process_handle,
            ctypes.c_void_p(addr),
            ctypes.byref(mbi),
            ctypes.sizeof(mbi)
        ):
            if mbi.State == MEM_COMMIT and mbi.Protect & PAGE_READABLE:
                try:
                    data = pm.read_bytes(addr, mbi.RegionSize)
                    index = data.find(pattern_bytes)
                    if index != -1:
                        return addr + index
                except:
                    pass
            addr += mbi.RegionSize
        else:
            break
    return None

# Main telemetry access class
class ICR2Telemetry:
    def __init__(self, version):
        self.pm = None
        self.exe_base = None  # Base address of loaded EXE module

        if version.upper() == "REND32A":
            window_keywords = ["program", "cart"]
            signature_bytes = bytes.fromhex("6C 69 63 65 6E 73 65 20 77 69 74 68 20 42 6F 62")
            self.signature_offset = int("b1c0c", 16)

            # Offsets from EXE base (Relative Virtual Addresses)
            self.lap_time_offset = int("d80fc", 16)
            self.session_time_offset = int("EF858", 16)
            self.dlong_offset = int("E0EB4", 16)
            self.cars_data_offset = int("E0E74", 16)
            self.engine_durability_offset = int("BB70C", 16)
            self.boost_offset = int("BB60A", 16)
            self.cars_data2_offset = int("E1624", 16)

        self.connect(window_keywords, signature_bytes)

    def get_engine_durability(self):
        return self.read_int(self.engine_durability_offset)

    def get_session_time(self):
        return self.read_int(self.session_time_offset)

    def get_boost(self):
        # Convert encoded 16-bit value to boost pressure in PSI
        boost = (self.read_uint16(self.boost_offset) - 17929) / 1616 + 29
        return boost

    def get_cars_data(self):
        """
        Returns a list of 40 car data entries.
        Each car has 12 fields of 4 bytes each.
        Field layout: data1, data2, data3, data4, dlong, dlat, data7, rotation, speed, tire_rotation, steering, data12
        """
        raw = self.read_uint_array(self.cars_data_offset, 40 * 12)
        cars = []
        for i in range(40):
            fields = raw[i * 12 : (i + 1) * 12]
            car = {
                "data1": fields[0],
                "data2": fields[1],
                "data3": fields[2],
                "data4": fields[3],
                "dlong": fields[4],
                "dlat": fields[5],
                "data7": fields[6],
                "rotation": fields[7],
                "speed": fields[8],
                "tire_rotation": fields[9],
                "steering": fields[10],
                "data12": fields[11],
            }
            cars.append(car)
        return cars

    def connect(self, keywords, pattern):
        result = find_pid_by_window_title(keywords)
        if not result:
            raise RuntimeError("Target window not found.")
        print(f"Connected to: '{result['title']}' (PID {result['pid']})")

        self.pm = pymem.Pymem()
        self.pm.open_process_from_id(result['pid'])

        found_addr = find_pattern_address(self.pm, pattern)
        if not found_addr:
            raise RuntimeError("Signature not found in memory.")

        self.exe_base = found_addr - self.signature_offset
        print(f"EXE base = {hex(self.exe_base)}")

    def read_uint16(self, exe_offset):
        """
        Read a 2-byte unsigned integer from memory at the given EXE-relative offset.
        :param exe_offset: Offset from the base of the loaded EXE
        """
        addr = self.exe_base + exe_offset
        raw = self.pm.read_bytes(addr, 2)
        return struct.unpack("<H", raw)[0]

    def read_uint(self, exe_offset):
        """Read a 4-byte unsigned integer from memory."""
        return self.pm.read_uint(self.exe_base + exe_offset)

    def read_int(self, exe_offset):
        """Read a 4-byte signed integer from memory."""
        return self.pm.read_int(self.exe_base + exe_offset)

    def read_float(self, exe_offset):
        """Read a 4-byte float from memory."""
        return self.pm.read_float(self.exe_base + exe_offset)

    def read_uint_array(self, exe_offset, count):
        """
        Read a list of 4-byte signed integers from memory.
        :param exe_offset: Offset from EXE base
        :param count: Number of integers to read
        """
        addr = self.exe_base + exe_offset
        raw = self.pm.read_bytes(addr, count * 4)
        return list(struct.unpack(f"<{count}i", raw))

    def close(self):
        """Close process handle and clean up."""
        if self.pm:
            self.pm.close_process()
