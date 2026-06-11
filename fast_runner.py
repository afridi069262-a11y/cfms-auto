"""
FAST RUNNER — Prosecution + Court + Framing of Charge + Judgment
=================================================================
Yeh script SIRF to_be_filled.txt padhta hai.
Har case ke liye ORDER:
  1. Prosecution create
  2. Court create
  2.5 Framing of Charge  ← NEW: FIR view API se offences fetch, phir framing API call
  3. Judgment / Final Order update

=============================================================
SCRIPT CHALANE SE PEHLE HAR BAAR YAHI KARO — SESSION FIX
=============================================================

  STEP 1: Browser mein login karo
          https://cfms.prosecution.punjab.gov.pk

  STEP 2: F12 → Network tab → page refresh → kisi request pe click
          Headers → Response Headers → "set-cookie" se:
              XSRF-TOKEN=eyJ...
              prosecution_department_of_punjab_session=eyJ...
          DONO copy karo

  STEP 3: api_session.json update karo:
          {
            "cookies": {
              "XSRF-TOKEN": "YAHAN_XSRF_PASTE_KARO",
              "prosecution_department_of_punjab_session": "YAHAN_SESSION_PASTE_KARO"
            },
            "xsrf_token": "XSRF_KI_WAHI_VALUE_DOBARA",
            "captured_at": "2026-03-20T10:00:00.000Z"
          }

  STEP 4: to_be_filled.txt format (TAB separated):
          Sr  [Extra]  FIR_No  Year  Offence          Station      Date        Decision
          1   200      22      379 PPC                Rang Mehal   01-01-24    Acquitted

  STEP 5: python3 fast_runner.py

  NOTE: Session sirf 2 GHANTE valid rehti hai.

=============================================================
FRAMING OF CHARGE — HOW IT WORKS (NEW):
  - FIR ka get-fir-view API call hota hai
  - Usme se har accused ki sections milti hain
  - Phir /framing-of-charge API pe POST hota hai
  - Agar koi accused section nahi mili → FIR ki original sections use hoti hain
  - Agar framing fail ho → warning log hoti hai, case continue rehta hai
=============================================================
INVALID CASES:
  - Parse error
  - FIR not found
  - Decision match fail
  - Judgment (Final Order) update fail → JUDGMENT_ERROR note ke saath
=============================================================
"""

import requests, json, os, time, logging, re, urllib.parse
from difflib import SequenceMatcher
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fast_runner.log"),
        logging.StreamHandler()
    ]
)

# ── File paths ─────────────────────────────────────────────
TO_BE_FILLED    = "to_be_filled.txt"
FILLED_ENTRIES  = "filled_entries.txt"
INVALID_CASES   = "invalid_cases.txt"
SESSION_FILE    = "api_session.json"

BASE_URL = "https://cfms.prosecution.punjab.gov.pk"

# ── Section ID Mapping (needed for parse_offences) ─────────
SECTION_ID_MAP = {
    "(2)337f": "306",
    "(2)337l": "320",
    "(337l (1": "1030",
    "(462j(d": "1535",
    "103": "1501",
    "106 ppc": "2475",
    "107": "752",
    "109": "4",
    "110": "7",
    "111": "8",
    "113": "9",
    "114": "10",
    "115": "11",
    "116": "12",
    "117": "13",
    "118": "14",
    "119": "15",
    "120": "22",
    "120a": "23",
    "120b": "24",
    "121": "791",
    "121a": "25",
    "122": "26",
    "123": "27",
    "123a": "28",
    "123b": "29",
    "124": "30",
    "124a": "31",
    "125": "32",
    "126": "33",
    "127": "34",
    "128": "35",
    "129": "36",
    "130": "38",
    "131": "39",
    "132": "40",
    "132a": "40",
    "132-a": "40",
    "132-3": "40",
    "1323": "40",
    "133": "41",
    "134": "42",
    "135": "43",
    "136": "44",
    "137": "45",
    "138": "46",
    "13ppc": "2917",
    "140": "52",
    "141": "3282",
    "142": "3264",
    "143": "53",
    "144": "54",
    "145": "55",
    "146": "2561",
    "147": "56",
    "148": "57",
    "149": "58",
    "14ppc": "2918",
    "150": "62",
    "151": "63",
    "152": "64",
    "153": "65",
    "153a": "66",
    "153b": "67",
    "154": "68",
    "155": "69",
    "156": "78",
    "157": "79",
    "158": "80",
    "160": "84",
    "161": "85",
    "162": "86",
    "163": "87",
    "164": "88",
    "165": "89",
    "165a": "90",
    "165b": "790",
    "166": "91",
    "166(2)": "3366",
    "167": "92",
    "168": "93",
    "169": "94",
    "170": "97",
    "171": "98",
    "171b": "789",
    "171c": "788",
    "171d": "787",
    "171e": "99",
    "171f": "100",
    "171g": "101",
    "171h": "102",
    "171i": "103",
    "171j": "104",
    "172": "105",
    "173": "106",
    "174": "107",
    "175": "108",
    "176": "109",
    "177": "110",
    "178": "111",
    "179": "112",
    "180": "117",
    "181": "118",
    "182": "119",
    "183": "120",
    "184": "121",
    "185": "122",
    "186": "123",
    "187": "124",
    "188": "125",
    "189": "126",
    "190": "131",
    "191": "132",
    "192": "3266",
    "193": "133",
    "194": "134",
    "195": "135",
    "196": "136",
    "197": "137",
    "198": "138",
    "199": "139",
    "2": "853",
    "200": "141",
    "201": "142",
    "202": "143",
    "203": "144",
    "204": "145",
    "205": "146",
    "206": "147",
    "207": "148",
    "208": "149",
    "209": "150",
    "210": "154",
    "211": "155",
    "212": "156",
    "213": "157",
    "214": "158",
    "215": "159",
    "216": "160",
    "216a": "161",
    "217": "162",
    "218": "163",
    "219": "164",
    "220": "167",
    "221": "168",
    "222": "169",
    "223": "170",
    "224": "171",
    "225": "172",
    "225a": "173",
    "225b": "174",
    "227": "176",
    "228": "177",
    "229": "178",
    "231": "180",
    "232": "181",
    "233": "182",
    "234": "183",
    "235": "184",
    "236": "185",
    "237": "186",
    "238": "187",
    "239": "188",
    "24": "842",
    "240": "190",
    "241": "191",
    "242": "192",
    "243": "193",
    "244": "194",
    "245": "195",
    "246": "196",
    "247": "197",
    "248": "198",
    "249": "199",
    "250": "200",
    "251": "201",
    "252": "202",
    "253": "203",
    "254": "204",
    "255": "205",
    "256": "206",
    "257": "207",
    "258": "208",
    "259": "209",
    "260": "212",
    "261": "213",
    "262": "214",
    "263": "215",
    "263a": "216",
    "264": "217",
    "265": "218",
    "266": "219",
    "267": "220",
    "268": "594",
    "269": "221",
    "270": "222",
    "271": "223",
    "272": "224",
    "273": "225",
    "274": "226",
    "275": "227",
    "276": "228",
    "277": "229",
    "278": "230",
    "279": "231",
    "280": "232",
    "281": "233",
    "282": "234",
    "283": "235",
    "284": "236",
    "285": "237",
    "286": "238",
    "287": "240",
    "288": "241",
    "289": "242",
    "290": "243",
    "291": "244",
    "292": "245",
    "292 (d)": "3321",
    "292-b": "3145",
    "292a": "960",
    "293": "246",
    "294": "247",
    "294a": "248",
    "294b": "249",
    "295": "250",
    "295a": "251",
    "295b": "252",
    "295c": "253",
    "296": "254",
    "297": "258",
    "297a": "259",
    "298": "262",
    "298a": "263",
    "298b": "264",
    "298c": "265",
    "299": "851",
    "3/4": "1052",
    "300": "793",
    "301": "794",
    "302": "277",
    "303": "795",
    "303(a)": "278",
    "303(b)": "279",
    "304": "796",
    "305": "797",
    "306": "798",
    "307": "800",
    "308": "282",
    "309": "801",
    "310": "802",
    "310a": "774",
    "311": "283",
    "312": "284",
    "313": "803",
    "314": "804",
    "315": "805",
    "316": "285",
    "317": "806",
    "318": "807",
    "319": "286",
    "320": "287",
    "321": "808",
    "322": "288",
    "323": "809",
    "324": "289",
    "325": "290",
    "326": "810",
    "327": "291",
    "328": "292",
    "328a": "1572",
    "329": "293",
    "330": "811",
    "331": "812",
    "332": "813",
    "333": "814",
    "334": "294",
    "335": "295",
    "335 (ii)": "2907",
    "336": "296",
    "336a": "2649",
    "336b": "297",
    "337": "815",
    "337 e (b)": "641",
    "337 u3": "2789",
    "337/l3": "901",
    "337a": "779",
    "337a(i)": "298",   "337a1": "298",   "337-a1": "298",   "337ai": "298",
    "337a(ii)": "299",  "337a2": "299",   "337-a2": "299",   "337aii": "299",
    "337a(iii)": "300", "337a3": "300",   "337-a3": "300",   "337aiii": "300",
    "337a(iv)": "301",  "337a4": "301",   "337-a4": "301",   "337aiv": "301",
    "337a(v)": "302",   "337a5": "302",   "337-a5": "302",   "337av": "302",
    "337a(vi)": "303",  "337a6": "303",   "337-a6": "303",   "337avi": "303",
    "337b": "816",
    "337b/2(a)": "2768",
    "337b/2(b)": "2769",
    "337c": "817",
    "337d": "304",
    "337d1": "3191",
    "337e": "818",
    "337e/2a": "2767",
    "337e1": "2618",
    "337e2c": "2401",
    "337f": "781",
    "337f(i)": "305",   "337f1": "305",   "337-f1": "305",   "337fi": "305",
    "337f(ii)": "306",  "337f2": "306",   "337-f2": "306",   "337fii": "306",
    "337f(iii)": "307", "337f3": "307",   "337-f3": "307",   "337fiii": "307",
    "337f(iv)": "308",  "337f4": "308",   "337-f4": "308",   "337fiv": "308",
    "337f(v)": "309",   "337f5": "309",   "337-f5": "309",   "337fv": "309",
    "337f(vi)": "310",  "337f6": "310",   "337-f6": "310",   "337fvi": "310",
    "337g": "311",
    "337h": "957",
    "337h(1)": "312",   "337h1": "312",   "337-h1": "312",
    "337h(2)": "313",   "337h2": "313",   "337-h2": "313",
    "337i": "315",
    "337j": "316",
    "337k": "317",
    "337l": "318",
    "337l(a)": "319",
    "337lb": "2581",
    "337m": "321",
    "337n": "322",
    "337o": "323",
    "337p": "324",
    "337q": "325",
    "337r": "326",
    "337s": "327",
    "337t": "328",
    "337t(1)": "3290",
    "337t(2)": "3303",
    "337u": "329",
    "337u ii": "2958",
    "337u1": "1858",
    "337v": "330",
    "337v(a)": "1396",
    "337v(b)": "2845",
    "337v2": "1127",
    "337w": "331",
    "337x": "332",
    "337y": "333",
    "337z": "334",
    "338": "746",
    "338-c(a)": "3267",
    "338-c(b)": "3268",
    "338-c(c)": "3269",
    "338a": "783",
    "338a(a)": "335",
    "338a(b)": "336",
    "338b": "337",
    "338c": "338",
    "338d": "339",
    "338e": "340",
    "338f": "341",
    "338g": "819",
    "338h": "820",
    "339": "342",
    "34": "344",
    "340": "821",
    "341": "345",
    "342": "346",
    "343": "347",
    "344": "348",
    "345": "349",
    "346": "350",
    "347": "351",
    "348": "352",
    "349": "822",
    "350": "662",
    "351": "823",
    "352": "353",
    "353": "354",
    "354": "355",
    "354a": "356",
    "355": "357",
    "356": "358",
    "357": "359",
    "358": "360",
    "359": "824",
    "360": "825",
    "361": "826",
    "362": "827",
    "363": "361",
    "364": "362",
    "364a": "363",
    "365": "364",
    "365a": "365",
    "365b": "366",
    "366": "367",
    "366a": "368",
    "366b": "369",
    "367": "370",
    "367a": "371",
    "368": "372",
    "369": "373",
    "369a": "3287",
    "370": "374",
    "371": "375",
    "371/ab": "878",
    "371a": "376",
    "371b": "377",
    "372": "378",
    "373": "379",
    "374": "380",
    "375": "627",
    "375a": "3315",
    "376": "381",
    "376(4)": "3291",
    "376(b)(3)": "3318",
    "376a": "2664",
    "376ai": "3198",
    "376b": "2277",
    "376i": "382",
    "376ii": "383",
    "376iii": "2018",
    "377": "384",
    "377a": "1630",
    "377b": "1631",
    "377e": "3331",
    "377f": "3343",
    "377ii": "1122",
    "378": "828",
    "379": "385",
    "380": "386",
    "381": "387",
    "381a": "388",
    "382": "389",
    "383": "390",
    "384": "391",
    "385": "392",
    "386": "393",
    "387": "394",
    "388": "395",
    "389": "396",
    "390": "829",
    "391": "830",
    "392": "397",
    "393": "398",
    "394": "399",
    "395": "400",
    "396": "401",
    "397": "402",
    "398": "403",
    "399": "404",
    "400": "420",
    "401": "421",
    "402": "422",
    "402a": "784",
    "402b": "785",
    "402c": "786",
    "403": "423",
    "404": "424",
    "405": "831",
    "406": "425",
    "407": "426",
    "408": "427",
    "409": "428",
    "410": "430",
    "411": "431",
    "412": "432",
    "413": "433",
    "414": "434",
    "415": "435",
    "416": "436",
    "417": "437",
    "418": "438",
    "419": "439",
    "420": "441",
    "421": "442",
    "422": "443",
    "423": "444",
    "424": "445",
    "425": "832",
    "426": "446",
    "427": "447",
    "428": "448",
    "429": "449",
    "430": "451",
    "431": "452",
    "432": "453",
    "433": "454",
    "434": "455",
    "435": "456",
    "436": "457",
    "437": "458",
    "438": "459",
    "439": "460",
    "440": "462",
    "441": "833",
    "442": "834",
    "443": "835",
    "444": "836",
    "445": "837",
    "446": "838",
    "447": "463",
    "448": "464",
    "449": "465",
    "450": "467",
    "451": "468",
    "452": "469",
    "453": "470",
    "454": "471",
    "455": "472",
    "456": "473",
    "457": "474",
    "458": "475",
    "459": "476",
    "460": "478",
    "461": "479",
    "462": "480",
    "462 i(2a)": "948",
    "462-i": "1241",
    "462-k": "2956",
    "462b": "481",
    "462c": "482",
    "462d": "483",
    "462e": "484",
    "462f": "1029",
    "462g": "854",
    "462h electricity act": "684",
    "462i (2)": "3367",
    "462j": "2966",
    "462j(a)": "3333",
    "462j(c)": "3057",
    "462j(e)": "3251",
    "462j(f)": "3253",
    "462k(a)": "3322",
    "462k(b)": "3323",
    "462k(c)": "3324",
    "462k(d)": "3325",
    "462k(e)": "3326",
    "462k(f)": "3327",
    "462k(g)": "3328",
    "462l": "706",
    "462l (c)": "3247",
    "462l (d)": "3362",
    "462l (g)": "3248",
    "462m": "2967",
    "462n": "855",
    "462o": "856",
    "464": "839",
    "465": "486",
    "466": "487",
    "467": "488",
    "468": "489",
    "469": "490",
    "471": "491",
    "472": "492",
    "473": "493",
    "474": "494",
    "475": "495",
    "476": "496",
    "477": "497",
    "477a": "498",
    "478": "499",
    "479": "500",
    "480": "501",
    "481": "2119",
    "482": "502",
    "483": "503",
    "484": "504",
    "485": "505",
    "486": "506",
    "487": "507",
    "488": "508",
    "489": "509",
    "489a": "510",
    "489b": "511",
    "489c": "512",
    "489d": "513",
    "489e": "514",
    "489f": "515",
    "489g": "1617",
    "491": "516",
    "493": "517",
    "493a": "1518",
    "494": "518",
    "495": "519",
    "496": "520",
    "496a": "521",
    "496b": "522",
    "496c": "523",
    "497": "524",
    "498": "525",
    "498a": "742",
    "498b": "931",
    "498c": "2875",
    "499": "2863",
    "500": "530",
    "501": "531",
    "502": "532",
    "502a": "533",
    "503": "2565",
    "504": "534",
    "505": "535",
    "505(1)(b)": "3302",
    "505(2)": "3283",
    "505-1(c)": "3316",
    "506": "536",
    "506 (a)": "2827",
    "506/b": "748",
    "506i": "537",
    "506ii": "538",
    "507": "539",
    "508": "540",
    "509": "541",
    "509(i)": "3254",
    "509(ii)": "3281",
    "510": "542",
    "511": "543",
    "75": "971",
    "85": "3311",
    "86": "557",
    "87": "558",
    "88": "559",
    "94": "852",
    "c-292": "921",
}
ACT_ID = "2"  # PPC = Act ID 2

# ── Decision Mapping ────────────────────────────────────────
DECISION_MAPPING = {
    "Agreed":                       ("Cancellation accepted by court", "Yes"),
    "Convicted":                    ("Conviction", "Other imprisonment"),
    "Fined":                        ("Conviction", "Fine only"),
    "Acquitted":                    ("Acquittal", "Poor Investigation"),
    "Acquitted Due to Compromised": ("Acquittal", "Due to Compromise"),
    "u/s 249-A":                    ("Acquittal", "Poor Investigation"),
    "u/s 249-A CrPC":               ("Acquittal", "Poor Investigation"),
    "u/s 345 Cr.P.C":               ("Acquittal", "Due to Compromise"),
    "Consign to Record u/s 512":    ("Consign to Record", "512 Cr.P.C"),
    "Consign to Record Room":       ("Consign to Record", "512 Cr.P.C"),
    "Probation":                    ("Conviction", "Other imprisonment"),
    "Dismissed":                    ("Acquittal", "Poor Investigation"),
    "داخل دفتر زیردفعہ512":         ("Consign to Record", "512 Cr.P.C"),
    "داخل دفتر":                    ("Consign to Record", "512 Cr.P.C"),
    "منظور شد":                     ("Cancellation accepted by court", "Yes"),
    "منظورشد":                      ("Cancellation accepted by court", "Yes"),
    "زیردفعہ 249-A":                ("Acquittal", "Poor Investigation"),
    "خارج شدبوجہ عدم پیروی":          ("Acquittal", "Poor Investigation"),
    "خارج شدبوجہ عدم پیروی‌":        ("Acquittal", "Poor Investigation"),
    "خارج شد":                      ("Acquittal", "Poor Investigation"),
    "خارج":                         ("Acquittal", "Poor Investigation"),
    "بری شدبصیغہ راضی نامہ":         ("Acquittal", "Due to Compromise"),
    "فیصلہ شد":                     ("Consign to Record", "Untraced Report"),
    "بری شد":                       ("Acquittal", "Poor Investigation"),
    "سزا شد":                       ("Conviction", "Other imprisonment"),
    "جزوی بری":                     ("Acquittal", "Poor Investigation"),
    "جزوی سزا":                     ("Conviction", "Other imprisonment"),
    "پروبیشن":                      ("Conviction", "Other imprisonment"),
}

# ── Police Station Mapping ─────────────────────────────────
POLICE_STATION_MAPPING = {
    "رنگ محل": "Rang Mehal", "Rang Mahal": "Rang Mehal", "Rang Mehal": "Rang Mehal",
    "نئی انارکلی": "New Anarkali", "New Anarkali": "New Anarkali",
    "لوہاری گیٹ": "Lohari Gate", "Lohari Gate": "Lohari Gate",
    "اکبری گیٹ": "Akbari Gate", "Akbari Gate": "Akbari Gate",
    "ٹبی‌سٹی": "Tibbi City", "ٹبی سٹی": "Tibbi City",
    "Tabi City": "Tibbi City", "Tibbi City": "Tibbi City",
    "مانگا منڈی": "Manga Mandi", "Manga Mandi": "Manga Mandi",
    "ما‌نگا‌منڈی": "Manga Mandi",
    "گلشن اقبال": "Gulshan Iqbal", "Gulshan Iqbal": "Gulshan Iqbal",
    "لوئر مال": "Lower Mall", "Lower Mall": "Lower Mall",
    "راوی روڈ": "Ravi Road", "Ravi Road": "Ravi Road",
    "Islam Pura": "Islampura", "اسلام پورہ": "Islampura", "Islampura": "Islampura",
    "ریلوے‌مغلپورہ": "Railway Mughalpura", "ریلوے مغلپورہ": "Railway Mughalpura",
    "Railway Mughalpura": "Railway Mughalpura",
    "Railway Mughal Pura": "Railway Mughalpura",
    "ریلوے‌مغل‌پورہ": "Railway Mughalpura",
    "بھاٹی‌گیٹ": "Bhati Gate", "بھاٹی گیٹ": "Bhati Gate", "Bhati Gate": "Bhati Gate",
    "اقبال‌ٹاؤن": "Iqbal Town", "اقبال ٹاؤن": "Iqbal Town", "Iqbal Town": "Iqbal Town",
    "اچھرہ": "Ichhara",
    "بادامی‌باغ": "Badami Bagh", "بادامی باغ": "Badami Bagh", "Badami Bagh": "Badami Bagh",
    "داتا‌دربار": "Data Darbar", "داتا دربار": "Data Darbar", "Data Darbar": "Data Darbar",
    "رائیونڈ": "Raiwind",
    "ساندہ": "Sanda",
    "سبزہ‌زار": "Sabzazar", "سبزہ زار": "Sabzazar", "Sabzazar": "Sabzazar",
    "سمن‌آباد": "Samnabad", "سمن آباد": "Samnabad", "Samnabad": "Samnabad",
    "سندر": "Sundar",
    "شاد‌باغ": "Shadbagh", "شاد باغ": "Shadbagh", "Shadbagh": "Shadbagh",
    "شاہدرہ": "Shahdara",
    "شاہدرہ‌ٹاؤن": "Shahdara Town", "شاہدرہ ٹاؤن": "Shahdara Town",
    "شفیق‌آباد": "Shafiqabad", "شفیق آباد": "Shafiqabad", "Shafiqabad": "Shafiqabad",
    "شیرا‌کوٹ": "Shera Kot", "شیرا کوٹ": "Shera Kot",
    "غالب‌مار‌کیٹ": "Ghalib Market", "غالب مارکیٹ": "Ghalib Market", "Ghalib Market": "Ghalib Market",
    "لاری‌اڈا": "Lari Adda", "لاری اڈا": "Lari Adda", "Lari Adda": "Lari Adda",
    "لیاقت‌آباد": "Liaqatabad", "لیاقت آباد": "Liaqatabad", "Liaqatabad": "Liaqatabad",
    "مز‌نگ": "Mozang", "مزنگ": "Mozang", "Mozang": "Mozang",
    "مستی‌گیٹ": "Masti Gate", "مستی گیٹ": "Masti Gate", "Masti Gate": "Masti Gate",
    "مصری‌شاہ": "Misri Shah", "مصری شاہ": "Misri Shah", "Misri Shah": "Misri Shah",
    "مو‌چی‌گیٹ": "Mochi Gate", "موچی گیٹ": "Mochi Gate", "Mochi Gate": "Mochi Gate",
    "نواں‌کوٹ": "Nawan Kot", "نواں کوٹ": "Nawan Kot", "Nawan Kot": "Nawan Kot",
    "نو‌لکھا": "Naulakha", "نولکھا": "Naulakha", "Naulakha": "Naulakha",
    "پرانی‌انارکلی": "Old Anarkali", "پرانی انارکلی": "Old Anarkali",
    "Purani Anarkali": "Old Anarkali", "Old Anarkali": "Old Anarkali",
    "چو‌ہنگ": "Chuhng", "چوہنگ": "Chuhng", "Chuhng": "Chuhng",
    "کاہنہ": "Kahna",
    "کرائم کنٹرول ڈیپارٹمنٹ-I": "Crime Control Dept-I",
    "کو‌ٹ‌لکھپت": "Kot Lakhpat", "کوٹ لکھپت": "Kot Lakhpat", "Kot Lakhpat": "Kot Lakhpat",
    "گرین‌ٹاؤن": "Green Town", "گرین ٹاؤن": "Green Town", "Green Town": "Green Town",
    "گلبرگ": "Gulberg",
    "گلشن‌راوی": "Gulshan Ravi", "گلشن راوی": "Gulshan Ravi", "Gulshan Ravi": "Gulshan Ravi",
    "گو‌الم‌نڈی": "Gowalmandi", "گوالمنڈی": "Gowalmandi", "Gowalmandi": "Gowalmandi",
    "ہنجر‌وال": "Hanjarwal", "ہنجروال": "Hanjarwal", "Hanjarwal": "Hanjarwal",
    "یکی‌گیٹ": "Yaki Gate", "یکی گیٹ": "Yaki Gate", "Yaki Gate": "Yaki Gate",
    "مصطفیٰ‌ٹاؤن": "Mustafa Town", "مصطفیٰ ٹاؤن": "Mustafa Town", "Mustafa Town": "Mustafa Town",
}

# ── Helpers ────────────────────────────────────────────────
norm = lambda t: (
    t.lower().replace(" ", "").replace("-", "").replace("_", "")
     .replace(".", "").replace("‌", "")
) if t else ""


def translate_station(s):
    s = s.strip()
    if s in POLICE_STATION_MAPPING:
        return POLICE_STATION_MAPPING[s]
    for k, v in POLICE_STATION_MAPPING.items():
        if s.lower() == k.lower():
            return v
    best, bs = None, 0.0
    for k, v in POLICE_STATION_MAPPING.items():
        sc = SequenceMatcher(None, norm(s), norm(k)).ratio()
        if sc > bs:
            bs, best = sc, v
    return best if best and bs >= 0.75 else s


def fuzzy_decision(raw):
    if not raw:
        return None
    cleaned = raw.lower().strip()
    best, bs = None, 0.0
    for key in DECISION_MAPPING:
        sc = SequenceMatcher(None, cleaned, key.lower()).ratio()
        if sc > bs:
            bs, best = sc, key
    return best if bs >= 0.50 else None


def parse_offences(offence_raw):
    raw = offence_raw.strip()
    peho_match = re.match(r'^(\d+/\d+)\s*peho', raw, re.IGNORECASE)
    if peho_match:
        sec_text = peho_match.group(1).lower()
        sec_id = SECTION_ID_MAP.get(sec_text)
        if sec_id:
            return [{"act_id": ACT_ID, "section_id": sec_id, "sub_section_id": None}]
        return []

    raw = re.sub(r'(\d{3,})/([A-Za-z]\d?)', r'\1\2', raw)
    raw = re.sub(r'(\d{3,})-([A-Za-z])-(\d)', r'\1\2\3', raw)
    raw = re.sub(r'(\d{3,})-([A-Za-z]\d)', r'\1\2', raw)
    raw = re.sub(r'(\d{3,}[A-Za-z])-?(\d)', r'\1\2', raw)

    if re.search(r'complaint\s*u/s\s*200', raw, re.IGNORECASE):
        return []

    pure_skip_patterns = [r'^\s*11\s*rent act\s*$', r'^\s*complaint\s*u/s',
                          r'^\s*13[-/]20[-/]65\s*$', r'^\s*13\s+20\s+65\s*$',
                          r'^\s*(the\s+)?punjab armed ordinance']
    for pat in pure_skip_patterns:
        if re.search(pat, raw, re.IGNORECASE):
            return []
    if re.search(r'rent act', raw, re.IGNORECASE) and not re.search(r'\d+\s*ppc|ppc\s*\d', raw, re.IGNORECASE):
        return []

    clean_raw = re.sub(r'\bppc\b|ppc\b|\bcr\.?p\.?c\.?\b', '', raw, flags=re.IGNORECASE)
    clean_raw = re.sub(r'[,\s]*\b13\s*\([^)]*\)\s*arms\s*[^,]*', '', clean_raw, flags=re.IGNORECASE)
    clean_raw = re.sub(r'[,\s]*arms\s*(ordinance|ord\.?|act)[^,]*', '', clean_raw, flags=re.IGNORECASE)
    clean_raw = re.sub(r'[,\s]*\b(a\.?o\.?)\b', '', clean_raw, flags=re.IGNORECASE)
    clean_raw = re.sub(r'[,\s]*13[\s]*[/\-][\s]*20[\s]*[/\-][\s]*65[\s]*', '', clean_raw)
    clean_raw = re.sub(r'[,\s]*13\s+20\s+65[\s]*', '', clean_raw)
    clean_raw = clean_raw.strip().strip(',').strip()

    parts = re.split(r'[,&+]|\band\b', clean_raw, flags=re.IGNORECASE)

    acts_hook, seen = [], set()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        sub_parts = re.split(r'(?<=[\dA-Za-z])[/\-](?=\d)', part)
        for sub in sub_parts:
            sub = sub.strip()
            if not sub:
                continue
            sec_norm = sub.lower().replace(" ", "").replace("_", "").replace(".", "")
            sec_norm = re.sub(r'(19|20)\d{2}$', '', sec_norm)
            sec_no_hyph = sec_norm.replace("-", "")
            sec_id = SECTION_ID_MAP.get(sec_no_hyph)
            if not sec_id:
                sec_id = SECTION_ID_MAP.get(sec_norm)
            if not sec_id:
                m = re.search(r'^(\d+[a-z]?(?:\(?[a-z0-9]*\))?)', sec_no_hyph)
                if m:
                    alt = m.group(1)
                    sec_id = SECTION_ID_MAP.get(alt)
                    if sec_id:
                        sec_no_hyph = alt
            if not sec_id:
                if not re.search(r'\d', sec_no_hyph):
                    continue
                continue
            if sec_id in seen:
                continue
            seen.add(sec_id)
            acts_hook.append({"act_id": ACT_ID, "section_id": sec_id, "sub_section_id": None})

    return acts_hook


# ── Line parser ────────────────────────────────────────────

def parse_case(line):
    fields = [f.strip() for f in line.split('\t') if f.strip()]

    if len(fields) >= 8:
        _, _, fir_no, fir_year, offence_raw, station_raw, date_str, raw_decision = fields[:8]
    elif len(fields) >= 7:
        _, fir_no, fir_year, offence_raw, station_raw, date_str, raw_decision = fields[:7]
    elif len(fields) == 6:
        _, fir_no, fir_year, offence_raw, station_raw = fields[:5]
        last = fields[5]
        if ':' in last:
            date_str, raw_decision = last.split(':', 1)
        else:
            raise ValueError("Bad 6-field format")
    else:
        raise ValueError(f"Need 6+ fields, got {len(fields)}")

    station = translate_station(station_raw)

    parts = date_str.replace('.', '-').split('-')
    if len(parts) == 3:
        d, m, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
        if len(y) == 2:
            y = "20" + y
        decision_date = f"{y}-{m}-{d}"
    else:
        raise ValueError(f"Bad date: {date_str}")

    decision_key = fuzzy_decision(raw_decision.strip())
    if not decision_key:
        raise ValueError(f"Cannot match decision: {raw_decision}")

    acts_hook = parse_offences(offence_raw)

    return {
        "fir_no": fir_no,
        "fir_year": fir_year[-2:],
        "fir_year_full": fir_year,
        "station": station,
        "offence_raw": offence_raw,
        "acts_hook": acts_hook,
        "decision_date": decision_date,
        "decision_key": decision_key,
    }


# ── Invalid case logger ────────────────────────────────────

def log_invalid(reason, case_line, extra=""):
    """
    Writes the original case line to invalid_cases.txt in exact same format
    as to_be_filled.txt — so it can be copied directly back for re-processing.
    Reason and extra are only written to the log, not the invalid_cases file.
    """
    import json as _json
    logging.info(f"Invalid reason: {reason}" + (f" | {extra}" if extra else ""))
    # structured event for UI table
    try:
        fields = [f.strip() for f in case_line.split('\t') if f.strip()]
        if len(fields) >= 7:
            fir_no   = fields[1] if len(fields) >= 8 else fields[1]
            fir_year = fields[2] if len(fields) >= 8 else fields[2]
            offence  = fields[3] if len(fields) >= 8 else fields[3]
            station  = fields[4] if len(fields) >= 8 else fields[4]
            decision = fields[6] if len(fields) >= 8 else fields[6]
        elif len(fields) >= 6:
            fir_no, fir_year, offence, station, decision = fields[1], fields[2], fields[3], fields[4], fields[5]
        else:
            fir_no = fir_year = offence = station = decision = "?"
        payload = _json.dumps({
            "fir": fir_no, "year": fir_year, "offence": offence,
            "station": station, "decision": decision, "reason": reason
        }, ensure_ascii=False)
        logging.info(f"CASE_INVALID:{payload}")
    except Exception:
        logging.info(f"CASE_INVALID:{{}}")
    with open(INVALID_CASES, 'a', encoding='utf-8') as f:
        f.write(case_line + '\n')


# ── API Session ────────────────────────────────────────────

class ApiSession:

    DECISION_IDS = {
        'Acquittal':                     {'id': 2, 'details': {'Poor Investigation': 14, 'Due to Compromise': 13, 'On merit': 12}},
        'Cancellation accepted by court': {'id': 4, 'details': {'Yes': 23, 'No': 24}},
        'Consign to Record':              {'id': 3, 'details': {'512 Cr.P.C': 20, '249 Cr.P.C': 19, 'Untraced Report': 22}},
        'Conviction':                     {'id': 1, 'details': {'Other imprisonment': 9, 'Fine only': 10, 'Death': 7, 'Life': 8}},
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/143.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/#/",
            "X-Requested-With": "XMLHttpRequest",
        })
        self.district_id       = 27
        self.prosecutor_id     = 698
        self.police_station_id = None
        self.all_stations      = {}

    def load_session(self):
        try:
            data = json.load(open(SESSION_FILE, encoding="utf-8"))
            cookies = data.get("cookies", {})
            xsrf_raw = cookies.get("XSRF-TOKEN", "")
            xsrf_decoded = urllib.parse.unquote(xsrf_raw)
            for name, value in cookies.items():
                self.session.cookies.set(name, value, domain="cfms.prosecution.punjab.gov.pk")
            self.session.headers["X-XSRF-TOKEN"] = xsrf_decoded
            logging.info(f"✅ {len(cookies)} cookies loaded")
            return len(cookies) > 0
        except Exception as e:
            logging.error(f"Session load failed: {e}")
            return False

    def refresh_xsrf(self):
        try:
            self.session.get(f"{BASE_URL}/", timeout=10)
            for cookie in self.session.cookies:
                if cookie.name == "XSRF-TOKEN":
                    decoded = urllib.parse.unquote(cookie.value)
                    self.session.headers["X-XSRF-TOKEN"] = decoded
                    return True
        except Exception as e:
            logging.error(f"XSRF refresh failed: {e}")
        return False

    def verify_session(self):
        try:
            r = self.session.get(f"{BASE_URL}/get-dashboard-stats", timeout=30)
            if r.status_code == 200:
                logging.info("✅ Session valid")
                self.refresh_xsrf()
                return True
            logging.error(f"Session invalid: {r.status_code}")
            return False
        except Exception as e:
            logging.error(f"Session check failed: {e}")
            return False

    def load_master_data(self):
        try:
            r = self.session.get(f"{BASE_URL}/get-all-policestations", timeout=10)
            if r.status_code == 200:
                stations = r.json()
                if isinstance(stations, list):
                    for s in stations:
                        self.all_stations[s.get('text', '').strip()] = s.get('id')
                logging.info(f"✅ {len(self.all_stations)} police stations loaded")
        except Exception as e:
            logging.error(f"Station load failed: {e}")

    def get_station_id(self, station_name):
        if station_name in self.all_stations:
            return self.all_stations[station_name]
        best, bs = None, 0.0
        for name, sid in self.all_stations.items():
            sc = SequenceMatcher(None, norm(station_name), norm(name)).ratio()
            if sc > bs:
                bs, best = sc, sid
        return best if best and bs >= 0.70 else None

    def fetch_fir_id(self, case):
        station_id = self.get_station_id(case['station'])
        if not station_id:
            station_id = case['station']
        self.police_station_id = station_id
        payload = {
            "fir_type": "police_station", "remote_fir_id": None,
            "fir_no": case['fir_no'], "year": case['fir_year'],
            "district_id": self.district_id,
            "police_station_id": str(station_id),
            "department_id": "", "registering_officer": "",
            "officer_designation": "", "narrative": "",
            "is_complaint": 0, "fir_date": "", "date_formated": "",
            "section_of_law": "", "sections": [], "date": "",
            "dept_police_station_id": "", "old_document": "", "document": "",
            "offences": [{"act_id": "", "section_id": "", "sub_section_id": "",
                          "act_sections": [], "act_section_subs": []}]
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }
        r = self.session.post(
            f"{BASE_URL}/fir_fetch_from_fir_system",
            json=payload, headers=headers, timeout=15, allow_redirects=False
        )
        if r.status_code in [301, 302, 303, 307, 308]:
            logging.error("FIR fetch redirect — session expired!")
            return None
        if r.status_code != 200:
            logging.error(f"FIR fetch {r.status_code}: {r.text[:200]}")
            return None
        try:
            data = r.json()
            fir_id = (data.get('fir_id') or data.get('id') or
                      (data.get('data', {}).get('id') if isinstance(data, dict) else None))
            if fir_id:
                logging.info(f"✅ fir_id={fir_id}")
                return fir_id
            match = re.search(r'"id"\s*:\s*(\d+)', r.text)
            if match:
                return int(match.group(1))
            logging.error(f"fir_id not found: {r.text[:400]}")
            return None
        except Exception as e:
            logging.error(f"FIR parse error: {e}")
            return None

    def create_prosecution(self, fir_id, case):
        try:
            from requests_toolbelt.multipart.encoder import MultipartEncoder
            m = MultipartEncoder(fields={
                'id': '', 'prosecutor_id': str(self.prosecutor_id),
                'from': case['decision_date'], 'to': case['decision_date'],
                'role_of_prosecutor': 'Conduct Trial',
                'fir_id': str(fir_id), 'district_id': str(self.district_id),
            })
            r = self.session.post(f"{BASE_URL}/prosecutor", data=m,
                                  headers={"Content-Type": m.content_type}, timeout=15)
        except ImportError:
            boundary = "WebKitFormBoundaryABC123"
            body = (
                f"------{boundary}\r\nContent-Disposition: form-data; name=\"id\"\r\n\r\n\r\n"
                f"------{boundary}\r\nContent-Disposition: form-data; name=\"prosecutor_id\"\r\n\r\n{self.prosecutor_id}\r\n"
                f"------{boundary}\r\nContent-Disposition: form-data; name=\"from\"\r\n\r\n{case['decision_date']}\r\n"
                f"------{boundary}\r\nContent-Disposition: form-data; name=\"to\"\r\n\r\n{case['decision_date']}\r\n"
                f"------{boundary}\r\nContent-Disposition: form-data; name=\"role_of_prosecutor\"\r\n\r\nConduct Trial\r\n"
                f"------{boundary}\r\nContent-Disposition: form-data; name=\"fir_id\"\r\n\r\n{fir_id}\r\n"
                f"------{boundary}\r\nContent-Disposition: form-data; name=\"district_id\"\r\n\r\n{self.district_id}\r\n"
                f"------{boundary}--\r\n"
            )
            r = self.session.post(
                f"{BASE_URL}/prosecutor", data=body.encode(),
                headers={"Content-Type": f"multipart/form-data; boundary=----{boundary}"},
                timeout=15
            )
        if r.status_code in [200, 201]:
            logging.info("✅ Prosecution created")
            return True
        logging.error(f"Prosecution failed: {r.status_code} {r.text[:200]}")
        return False

    def create_court(self, fir_id):
        boundary = "WebKitFormBoundaryXYZ789"
        body = (
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"id\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"court_type\"\r\n\r\nmagistrate\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"court_name\"\r\n\r\nSection 30 Magistrate\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"court_number\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"name_of_magistrate\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"orders_of_judge\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"name_of_judge\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"type_presiding_officer\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"name_presiding_officer\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"orders_regarding_police_report\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"fir_id\"\r\n\r\n{fir_id}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"transferMode\"\r\n\r\nfalse\r\n"
            f"------{boundary}--\r\n"
        )
        r = self.session.post(
            f"{BASE_URL}/court-fir", data=body.encode(),
            headers={"Content-Type": f"multipart/form-data; boundary=----{boundary}"},
            timeout=15
        )
        if r.status_code in [200, 201]:
            logging.info("✅ Court created")
            return True
        logging.error(f"Court failed: {r.status_code} {r.text[:200]}")
        return False

    def get_fir_view(self, fir_id):
        """
        GET /fir/get-fir-view/{fir_id}
        Returns full FIR data including accuseds with their accused_sections.
        Used to extract offences for Framing of Charge.
        """
        try:
            r = self.session.get(
                f"{BASE_URL}/fir/get-fir-view/{fir_id}",
                timeout=15
            )
            if r.status_code != 200:
                logging.error(f"get-fir-view failed: {r.status_code}")
                return None
            data = r.json()
            logging.info(f"FIR view fetched for fir_id={fir_id}")
            return data
        except Exception as e:
            logging.error(f"get-fir-view exception: {e}")
            return None

    def do_framing_of_charge(self, fir_id, fir_data, decision_date):
        """
        Framing of Charge — PUT /framing-of-charge/{accused_id}
        multipart/form-data with ActsHook JSON array
        """
        if not fir_data:
            logging.warning("Framing: no FIR data — skipping")
            return False

        accuseds     = fir_data.get("accuseds", [])
        fir_sections = fir_data.get("sections", [])

        if not accuseds:
            logging.warning("Framing: no accuseds in FIR view — skipping")
            return False

        fir_acts_hook = [
            {
                "act_id":        s.get("act_id"),
                "section_id":    s.get("section_id"),
                "sub_section_id": s.get("sub_section_id") or ""
            }
            for s in fir_sections
        ]

        DEFAULT_ASSESSMENT = (
            "The Prosecution has ocular account , recovery memo and arrest of accused in this case. "
            "Prosecution has direct evidence in the shape of statements of witness\u2019s u/s161 Cr.PC and 154 CrPC. "
            "Corroborative evidence in the shape of recovery memo of case property which is also admissible piece of evidence. "
            "Prosecution has also explanatory evidence in the shape of site plan which fully explains the facts as narrated in FIR. "
            "All available evidence is admissible according to Q.S.O 1984. There is sufficient incriminating material available "
            "which prima facie connect the accused with the commission of offence. The available evidence is enough to conduct "
            "the trial of the accused for the proposed charges. Therefore, the case against accused is recommended for trial "
            "& trial of that accused person is in public interest."
        )

        any_success = False
        for accused in accuseds:
            accused_id   = accused.get("id")
            accused_name = accused.get("name", "")

            acc_secs = accused.get("accused_sections", [])
            if acc_secs:
                acts_hook = [
                    {
                        "act_id":        s.get("act_id"),
                        "section_id":    s.get("section_id"),
                        "sub_section_id": s.get("sub_section_id") or ""
                    }
                    for s in acc_secs
                ]
                logging.info(f"Framing: '{accused_name}' → {len(acts_hook)} accused section(s)")
            elif fir_acts_hook:
                acts_hook = fir_acts_hook
                logging.info(f"Framing: '{accused_name}' → {len(acts_hook)} FIR section(s) [fallback]")
            else:
                logging.warning(f"Framing: '{accused_name}' → no sections, skipping")
                continue

            assessment = accused.get("prosecutors_assessment_regarding_evidence") or DEFAULT_ASSESSMENT

            data = {
                "ids":                                       str(accused_id),
                "name_of_accused":                           accused_name,
                "prosecutors_assessment_regarding_evidence": assessment,
                "charge_supported_by_the_prosecutor":        "",
                "fir_id":                                    str(fir_id),
                "ActsHook":                                  json.dumps(acts_hook),
                "date_of_charge_by_court":                   "",
                "plea_id":                                   "",
                "sections":                                  "",
                "framing_of_charge":                         "",
                "applyTo":                                   "",
                "id":                                        str(accused_id),
                "_method":                                   "PUT",
            }

            try:
                r = self.session.post(
                    f"{BASE_URL}/framing-of-charge/{accused_id}",
                    data=data,
                    timeout=15
                )
                if r.status_code in [200, 201]:
                    logging.info(f"✅ Framing of Charge saved: '{accused_name}' (accused_id={accused_id})")
                    any_success = True
                else:
                    logging.warning(f"Framing failed '{accused_name}': {r.status_code} {r.text[:300]}")
            except Exception as e:
                logging.warning(f"Framing exception: {e}")

        return any_success

    def get_judgment_entries(self, fir_id):
        r = self.session.get(
            f"{BASE_URL}/judgment/{fir_id}?page=1&search=&length=10&column=id&dir=desc",
            timeout=10
        )
        if r.status_code != 200:
            logging.error(f"Judgment fetch failed: {r.status_code}")
            return []
        try:
            data = r.json()
            entries = data.get('data', data) if isinstance(data, dict) else data
            if isinstance(entries, list):
                logging.info(f"✅ {len(entries)} judgment entries")
                return entries
            return []
        except:
            return []

    def update_judgment(self, fir_id, entry, case):
        decision_key = case['decision_key']
        decision_text, detail_text = DECISION_MAPPING[decision_key]

        accused_id       = entry.get('accused_id') or entry.get('id')
        entry_id         = entry.get('id')
        accused_sections = entry.get('accused_sections', [])
        dec_info         = self.DECISION_IDS.get(decision_text, {})
        decision_id      = dec_info.get('id')
        detail_id        = dec_info.get('details', {}).get(detail_text)

        if accused_sections and decision_id:
            for sec in accused_sections:
                sec['nature_of_decision_id'] = str(decision_id)
                if detail_id:
                    sec['detail_of_decision_id'] = str(detail_id)

        is_cancellation          = 1 if "Cancellation" in decision_text else 0
        is_cancellation_accepted = str(detail_id) if is_cancellation and detail_id else ""
        accused_sections_str     = json.dumps(accused_sections, ensure_ascii=False)

        boundary = "WebKitFormBoundaryFAST123"
        body = (
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"id\"\r\n\r\n{entry_id}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"fir_id\"\r\n\r\n{fir_id}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"accused_id\"\r\n\r\n{accused_id}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"accused_name\"\r\n\r\n{entry.get('accused_name','')}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"accused_sections\"\r\n\r\n{accused_sections_str}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"date_of_judgment\"\r\n\r\n{case['decision_date']}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"applyAll\"\r\n\r\ntrue\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"is_cancellation\"\r\n\r\n{is_cancellation}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"is_cancellation_accepted\"\r\n\r\n{is_cancellation_accepted}\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"is_withdrawl\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"compensation\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"remarks\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"crpc_540_required\"\r\n\r\nno\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"crpc_540_remarks\"\r\n\r\n\r\n"
            f"------{boundary}\r\nContent-Disposition: form-data; name=\"_method\"\r\n\r\nPUT\r\n"
            f"------{boundary}--\r\n"
        )
        r = self.session.post(
            f"{BASE_URL}/judgment/{entry_id}", data=body.encode(),
            headers={"Content-Type": f"multipart/form-data; boundary=----{boundary}"},
            timeout=15
        )
        if r.status_code in [200, 201]:
            logging.info(f"✅ Judgment updated: entry {entry_id}")
            return True
        logging.error(f"Judgment update failed: {r.status_code} {r.text[:300]}")
        return False



# ── Case processor ─────────────────────────────────────────

def process_case(api, case_line):
    """
    1. Prosecution
    2. Court
    2.5 Framing of Charge (FIR view se offences fetch → framing API)
    3. Judgment
       YES → COMPLETE
       NO  → INVALID (log to invalid_cases.txt)

    Returns: status string
    """
    try:
        case = parse_case(case_line)
    except Exception as e:
        logging.error(f"Parse failed: {e}")
        log_invalid("PARSE_ERROR", case_line, str(e))
        return "SKIP"

    case_label = f"FIR {case['fir_no']}/{case['fir_year_full']} | {case['station']}"

    logging.info(
        f"\n{'='*60}\n"
        f"{case_label} | Offence: {case['offence_raw']} | "
        f"Decision: {case['decision_key']}\n"
        f"{'='*60}"
    )

    fir_id = api.fetch_fir_id(case)
    if not fir_id:
        logging.error("FIR not found — skipping")
        log_invalid("FIR_NOT_FOUND", case_line)
        return "SKIP"

    # ── STEP 1: Prosecution ────────────────────────────────
    logging.info("─── STEP 1: Prosecution ───")
    try:
        if not api.create_prosecution(fir_id, case):
            logging.warning("Prosecution failed — continuing")
    except Exception as e:
        logging.warning(f"Prosecution exception (continuing): {e}")

    # ── STEP 2: Court ──────────────────────────────────────
    logging.info("─── STEP 2: Court ───")
    try:
        if not api.create_court(fir_id):
            logging.warning("Court failed — continuing")
    except Exception as e:
        logging.warning(f"Court exception (continuing): {e}")


    # ── STEP 2.5: Framing of Charge ─────────────────────────────────
    logging.info("─── STEP 2.5: Framing of Charge ───")
    try:
        fir_data = api.get_fir_view(fir_id)
        if fir_data:
            framing_ok = api.do_framing_of_charge(fir_id, fir_data, case['decision_date'])
            if framing_ok:
                logging.info("✅ Framing of Charge completed")
            else:
                logging.warning("⚠️  Framing of Charge: no accused succeeded — continuing")
        else:
            logging.warning("⚠️  FIR view fetch failed for framing — continuing")
    except Exception as e:
        logging.warning(f"Framing of Charge exception (continuing): {e}")

    # ── STEP 3: Judgment ───────────────────────────────────
    logging.info("─── STEP 3: Judgment (Final Order) ───")
    entries = api.get_judgment_entries(fir_id)
    if not entries:
        logging.warning("No judgment entries — noting in invalid")
        log_invalid("NO_JUDGMENT_ENTRIES", case_line,
                    f"FIR={case['fir_no']}/{case['fir_year_full']} station={case['station']}")
        return "INVALID"

    decision_key    = case['decision_key']
    is_cancellation = "Cancellation" in DECISION_MAPPING[decision_key][0]
    targets         = entries[:1] if is_cancellation else entries

    judgment_errors = []
    for entry in targets:
        if not api.update_judgment(fir_id, entry, case):
            judgment_errors.append(f"entry {entry.get('id','')} ({entry.get('accused_name','')})")

    if judgment_errors:
        logging.error("❌ Judgment update failed")
        log_invalid(
            "JUDGMENT_ERROR", case_line,
            f"FIR={case['fir_no']}/{case['fir_year_full']} station={case['station']} "
            f"decision={case['decision_key']} failed_entries=[{'; '.join(judgment_errors)}]"
        )
        return "INVALID"


    logging.info(f"✅ Case complete: {case_label}")
    return "COMPLETE"


# ── Queue helpers ──────────────────────────────────────────

def mark_filled(line):
    with open(FILLED_ENTRIES, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    with open(TO_BE_FILLED, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(TO_BE_FILLED, 'w', encoding='utf-8') as f:
        f.write(lines[0])
        if len(lines) > 2:
            f.writelines(lines[2:])


# ── Main ───────────────────────────────────────────────────

def main():
    logging.info("=" * 60)
    logging.info("FAST RUNNER — Prosecution + Court + Judgment")
    logging.info("(Framing ke liye framing_runner.py chalao)")
    logging.info("Input: to_be_filled.txt")
    logging.info("=" * 60)

    api = ApiSession()

    if not api.load_session():
        logging.error("❌ api_session.json load failed — upar wali instructions follow karo")
        return

    api.refresh_xsrf()
    api.load_master_data()

    # ── Startup baseline ───────────────────────────────────

    total, success, skip, invalid = 0, 0, 0, 0

    while True:
        try:
            with open(TO_BE_FILLED, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except FileNotFoundError:
            logging.error(f"❌ '{TO_BE_FILLED}' file nahi mili")
            break

        if len(lines) <= 1:
            logging.info("✅ All cases processed!")
            break

        case_line = lines[1].strip()
        if not case_line:
            break

        total += 1
        status = process_case(api, case_line)

        if status == "COMPLETE":
            mark_filled(case_line)
            success += 1
        elif status == "SKIP":
            mark_filled(case_line)
            skip += 1
        elif status == "INVALID":
            mark_filled(case_line)
            invalid += 1

        logging.info(
            f"Progress: {success} done, {skip} skipped, "
            f"{invalid} invalid (not in dashboard) | Total: {total}"
        )
        time.sleep(1)

    logging.info(
        f"\n{'='*60}\n"
        f"FINISHED: {success} success, {skip} skipped, "
        f"{invalid} invalid (not reflected in dashboard)\n"
        f"{'='*60}"
    )


if __name__ == "__main__":
    main()
