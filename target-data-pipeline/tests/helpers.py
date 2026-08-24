def dataset(values=None, statuses=None):
    if values is None:
        values = [65, 53, 7, 6, 7, 2]
    result = {
        "version": "2.0",
        "class": "dataset",
        "id": [
            "ContentsCode",
            "Region",
            "Typ av influensa",
            "Mått",
            "Kön",
            "År och vecka",
        ],
        "size": [1, 3, 1, 1, 1, 2],
        "dimension": {
            "ContentsCode": {
                "category": {
                    "index": {"EliminatedValue": 0},
                    "label": {"EliminatedValue": "Reported cases"},
                }
            },
            "Region": {
                "category": {
                    "index": {"00": 0, "12": 1, "14": 2},
                    "label": {
                        "00": "Riket",
                        "12": "Skåne",
                        "14": "Västra Götaland",
                    },
                }
            },
            "Typ av influensa": {
                "category": {"index": {"1+2": 0}, "label": {"1+2": "Totalt"}}
            },
            "Mått": {
                "category": {
                    "index": {"1": 0},
                    "label": {"1": "Antal rapporterade fall"},
                }
            },
            "Kön": {
                "category": {
                    "index": {"1+2+0": 0},
                    "label": {"1+2+0": "Totalt"},
                }
            },
            "År och vecka": {
                "category": {
                    "index": {"2026W19": 0, "2026W20": 1},
                    "label": {"2026W19": "2026 v 19", "2026W20": "2026 v 20"},
                }
            },
        },
        "value": values,
    }
    if statuses is not None:
        result["status"] = statuses
    return result


def metadata():
    return {
        "title": "Influenza",
        "variables": [
            {
                "code": "Region",
                "values": ["00", "12", "14"],
                "valueTexts": ["Riket", "Skåne", "Västra Götaland"],
            },
            {"code": "Typ av influensa", "values": ["1+2"]},
            {"code": "Mått", "values": ["1"]},
            {"code": "Kön", "values": ["1+2+0"]},
            {"code": "År och vecka", "values": ["2026W19", "2026W20"]},
        ],
    }
