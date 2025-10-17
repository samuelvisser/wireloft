from enum import Enum


# DailyWire membership levels + WL custom types
class WlDwMembershipLevel(Enum):
    # WireLoft - specific type to allow any membership level
    WL_ANY = "WL_ANY"

    # DailyWire
    FREE = "FREE"
    READER = "READER"
    INSIDER = "INSIDER"
    INSIDER_PLUS = "INSIDER_PLUS"
    ALL_ACCESS = "ALL_ACCESS"