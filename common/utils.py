from enum import Enum


class Icons(Enum):
    ALERT = ":information_source:"
    ERROR = ":no_entry:"
    HMM = ":eyes:"
    SUCCESS = ":ballot_box_with_check:"
    WARN = ":warning:"

    def __str__(self):
        return str(self.value)
