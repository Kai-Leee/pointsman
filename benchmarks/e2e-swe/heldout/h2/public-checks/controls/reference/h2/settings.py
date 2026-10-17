import enum


class SettingCodes(enum.IntEnum):
    HEADER_TABLE_SIZE = 1
    ENABLE_PUSH = 2
    MAX_CONCURRENT_STREAMS = 3
    INITIAL_WINDOW_SIZE = 4
    MAX_FRAME_SIZE = 5
    MAX_HEADER_LIST_SIZE = 6


class ChangedSetting:
    def __init__(self, setting, original_value, new_value):
        self.setting = setting
        self.original_value = original_value
        self.new_value = new_value

    def __repr__(self):
        return f"ChangedSetting({self.setting!r}, {self.original_value!r}, {self.new_value!r})"
