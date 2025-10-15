from enum import Enum


class DwMembershipLevel(Enum):
    # WireLoft - specific type to allow any membership level
    WL_ANY = "WL_ANY"
    FREE = "FREE"
    READER = "READER"
    INSIDER = "INSIDER"
    INSIDER_PLUS = "INSIDER_PLUS"
    ALL_ACCESS = "ALL_ACCESS"