"""
South Korea province reference data.

This file owns province lookup, detection, and English/ID translation
mapping for all 17 Korean metropolitan cities and provinces.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from crawling.KR.models import ProvinceReference

PROVINCES: Final[tuple[ProvinceReference, ...]] = (
    ProvinceReference("KR-11", "서울특별시", "Seoul", "Capital"),
    ProvinceReference("KR-26", "부산광역시", "Busan", "Yeongnam"),
    ProvinceReference("KR-27", "대구광역시", "Daegu", "Yeongnam"),
    ProvinceReference("KR-28", "인천광역시", "Incheon", "Capital"),
    ProvinceReference("KR-29", "광주광역시", "Gwangju", "Honam"),
    ProvinceReference("KR-30", "대전광역시", "Daejeon", "Chungcheong"),
    ProvinceReference("KR-31", "울산광역시", "Ulsan", "Yeongnam"),
    ProvinceReference("KR-36", "세종특별자치시", "Sejong", "Chungcheong"),
    ProvinceReference("KR-41", "경기도", "Gyeonggi-do", "Capital"),
    ProvinceReference("KR-42", "강원특별자치도", "Gangwon State", "Gangwon"),
    ProvinceReference("KR-43", "충청북도", "Chungcheongbuk-do", "Chungcheong"),
    ProvinceReference("KR-44", "충청남도", "Chungcheongnam-do", "Chungcheong"),
    ProvinceReference("KR-45", "전북특별자치도", "Jeonbuk State", "Honam"),
    ProvinceReference("KR-46", "전라남도", "Jeollanam-do", "Honam"),
    ProvinceReference("KR-47", "경상북도", "Gyeongsangbuk-do", "Yeongnam"),
    ProvinceReference("KR-48", "경상남도", "Gyeongsangnam-do", "Yeongnam"),
    ProvinceReference("KR-50", "제주특별자치도", "Jeju", "Jeju"),
)

# Pre-defined mapping of Korean municipality names to their English romanized names
# and unique IDs to avoid scraping English/Japanese Wikipedia pages.
MUNICIPALITY_EN_MAP: Final[dict[str, str]] = {
    # ──────────────────────────────────────────────
    # Gangwon-do (KR-42) — EXISTING, DO NOT MODIFY
    # ──────────────────────────────────────────────
    "춘천시": "CHUNCHEON",
    "원주시": "WONJU",
    "강릉시": "GANGNEUNG",
    "동해시": "DONGHAE",
    "태백시": "TAEBAEK",
    "속초시": "SOKCHO",
    "삼척시": "SAMCHEOK",
    "홍천군": "HONGCHEON",
    "횡성군": "HOENGSEONG",
    "영월군": "YEONGWOL",
    "평창군": "PYEONGCHANG",
    "정선군": "JEONGSEON",
    "철원군 (대한민국)": "CHEORWON",
    "화천군": "HWACHEON",
    "양구군": "YANGGU",
    "인제군": "INJE",
    "고성군 (강원특별자치도)": "GOSEONG-GANGWON",
    "양양군": "YANGYANG",
    # ────────────────────────────────────────────────────
    # Gyeongsangbuk-do (KR-47) — EXISTING, DO NOT MODIFY
    # ────────────────────────────────────────────────────
    "포항시": "POHANG",
    "경주시": "GYEONGJU",
    "김천시": "GIMCHEON",
    "안동시": "ANDONG",
    "구미시": "GUMI",
    "영주시": "YEONGJU",
    "영천시": "YEONGCHEON",
    "상주시": "SANGJU",
    "문경시": "MUNGYEONG",
    "경산시": "GYEONGSAN",
    "의성군": "UISEONG",
    "청송군": "CHEONGSONG",
    "영양군": "YEONGYANG",
    "영덕군": "YEONGDEOK",
    "청도군": "CHEONGDO",
    "고령군": "GORYEONG",
    "성주군": "SEONGJU",
    "칠곡군": "CHILGOK",
    "예천군": "YECHEON",
    "봉화군": "BONGHWA",
    "울진군": "ULJIN",
    "울릉군": "ULLEUNG",
    # ──────────────────────────────────────────────
    # Seoul (KR-11) — 25 gu
    # ──────────────────────────────────────────────
    "종로구": "JONGNO",
    "중구 (서울특별시)": "JUNG-SEOUL",
    "용산구": "YONGSAN",
    "성동구": "SEONGDONG",
    "광진구": "GWANGJIN",
    "동대문구": "DONGDAEMUN",
    "중랑구": "JUNGNANG",
    "성북구": "SEONGBUK",
    "강북구": "GANGBUK",
    "도봉구": "DOBONG",
    "노원구": "NOWON",
    "은평구": "EUNPYEONG",
    "서대문구": "SEODAEMUN",
    "마포구": "MAPO",
    "양천구": "YANGCHEON",
    "강서구 (서울특별시)": "GANGSEO-SEOUL",
    "구로구": "GURO",
    "금천구": "GEUMCHEON",
    "영등포구": "YEONGDEUNGPO",
    "동작구": "DONGJAK",
    "관악구": "GWANAK",
    "서초구": "SEOCHO",
    "강남구": "GANGNAM",
    "송파구": "SONGPA",
    "강동구": "GANGDONG",
    # ──────────────────────────────────────────────
    # Busan (KR-26) — 15 gu + 1 gun
    # ──────────────────────────────────────────────
    "중구 (부산광역시)": "JUNG-BUSAN",
    "서구 (부산광역시)": "SEO-BUSAN",
    "동구 (부산광역시)": "DONG-BUSAN",
    "영도구": "YEONGDO",
    "부산진구": "BUSANJIN",
    "동래구": "DONGNAE",
    "남구 (부산광역시)": "NAM-BUSAN",
    "북구 (부산광역시)": "BUK-BUSAN",
    "해운대구": "HAEUNDAE",
    "사하구": "SAHA",
    "금정구": "GEUMJEONG",
    "강서구 (부산광역시)": "GANGSEO-BUSAN",
    "연제구": "YEONJE",
    "수영구": "SUYEONG",
    "사상구": "SASANG",
    "기장군": "GIJANG",
    # ──────────────────────────────────────────────
    # Daegu (KR-27) — 6 gu + 1 gun + 달서구
    # ──────────────────────────────────────────────
    "중구 (대구광역시)": "JUNG-DAEGU",
    "동구 (대구광역시)": "DONG-DAEGU",
    "서구 (대구광역시)": "SEO-DAEGU",
    "남구 (대구광역시)": "NAM-DAEGU",
    "북구 (대구광역시)": "BUK-DAEGU",
    "수성구": "SUSEONG",
    "달서구": "DALSEO",
    "달성군": "DALSEONG",
    "군위군": "GUNWI",
    # ──────────────────────────────────────────────
    # Incheon (KR-28) — 8 gu + 2 gun
    # ──────────────────────────────────────────────
    "중구 (인천광역시)": "JUNG-INCHEON",
    "동구 (인천광역시)": "DONG-INCHEON",
    "미추홀구": "MICHUHOL",
    "연수구": "YEONSU",
    "남동구": "NAMDONG",
    "부평구": "BUPYEONG",
    "계양구": "GYEYANG",
    "서구 (인천광역시)": "SEO-INCHEON",
    "강화군": "GANGHWA",
    "옹진군": "ONGJIN",
    # ──────────────────────────────────────────────
    # Gwangju (KR-29) — 5 gu
    # ──────────────────────────────────────────────
    "동구 (광주광역시)": "DONG-GWANGJU",
    "서구 (광주광역시)": "SEO-GWANGJU",
    "남구 (광주광역시)": "NAM-GWANGJU",
    "북구 (광주광역시)": "BUK-GWANGJU",
    "광산구": "GWANGSAN",
    # ──────────────────────────────────────────────
    # Daejeon (KR-30) — 5 gu
    # ──────────────────────────────────────────────
    "동구 (대전광역시)": "DONG-DAEJEON",
    "중구 (대전광역시)": "JUNG-DAEJEON",
    "서구 (대전광역시)": "SEO-DAEJEON",
    "유성구": "YUSEONG",
    "대덕구": "DAEDEOK",
    # ──────────────────────────────────────────────
    # Ulsan (KR-31) — 4 gu + 1 gun
    # ──────────────────────────────────────────────
    "중구 (울산광역시)": "JUNG-ULSAN",
    "남구 (울산광역시)": "NAM-ULSAN",
    "동구 (울산광역시)": "DONG-ULSAN",
    "북구 (울산광역시)": "BUK-ULSAN",
    "울주군": "ULJU",
    # ──────────────────────────────────────────────
    # Sejong (KR-36) — 1
    # ──────────────────────────────────────────────
    "세종특별자치시": "SEJONG",
    # ──────────────────────────────────────────────
    # Gyeonggi-do (KR-41) — 28 si + 3 gun
    # ──────────────────────────────────────────────
    "수원시": "SUWON",
    "성남시": "SEONGNAM",
    "의정부시": "UIJEONGBU",
    "안양시": "ANYANG",
    "부천시": "BUCHEON",
    "광명시": "GWANGMYEONG",
    "평택시": "PYEONGTAEK",
    "동두천시": "DONGDUCHEON",
    "안산시": "ANSAN",
    "고양시": "GOYANG",
    "과천시": "GWACHEON",
    "구리시": "GURI",
    "남양주시": "NAMYANGJU",
    "오산시": "OSAN",
    "시흥시": "SIHEUNG",
    "군포시": "GUNPO",
    "의왕시": "UIWANG",
    "하남시": "HANAM",
    "용인시": "YONGIN",
    "파주시": "PAJU",
    "이천시": "ICHEON",
    "안성시": "ANSEONG",
    "김포시": "GIMPO",
    "화성시": "HWASEONG",
    "광주시 (경기도)": "GWANGJU-GYEONGGI",
    "양주시": "YANGJU",
    "포천시": "POCHEON",
    "여주시": "YEOJU",
    "연천군": "YEONCHEON",
    "가평군": "GAPYEONG",
    "양평군": "YANGPYEONG",
    # ──────────────────────────────────────────────
    # Chungcheongbuk-do (KR-43) — 3 si + 8 gun
    # ──────────────────────────────────────────────
    "청주시": "CHEONGJU",
    "충주시": "CHUNGJU",
    "제천시": "JECHEON",
    "보은군": "BOEUN",
    "옥천군": "OKCHEON",
    "영동군": "YEONGDONG",
    "증평군": "JEUNGPYEONG",
    "진천군": "JINCHEON",
    "괴산군": "GOESAN",
    "음성군": "EUMSEONG",
    "단양군": "DANYANG",
    # ──────────────────────────────────────────────
    # Chungcheongnam-do (KR-44) — 8 si + 7 gun
    # ──────────────────────────────────────────────
    "천안시": "CHEONAN",
    "공주시": "GONGJU",
    "보령시": "BORYEONG",
    "아산시": "ASAN",
    "서산시": "SEOSAN",
    "논산시": "NONSAN",
    "계룡시": "GYERYONG",
    "당진시": "DANGJIN",
    "금산군": "GEUMSAN",
    "부여군": "BUYEO",
    "서천군": "SEOCHEON",
    "청양군": "CHEONGYANG",
    "홍성군": "HONGSEONG",
    "예산군": "YESAN",
    "태안군": "TAEAN",
    # ──────────────────────────────────────────────
    # Jeonbuk (KR-45) — 6 si + 8 gun
    # ──────────────────────────────────────────────
    "전주시": "JEONJU",
    "군산시": "GUNSAN",
    "익산시": "IKSAN",
    "정읍시": "JEONGEUP",
    "남원시": "NAMWON",
    "김제시": "GIMJE",
    "완주군": "WANJU",
    "진안군": "JINAN",
    "무주군": "MUJU",
    "장수군": "JANGSU",
    "임실군": "IMSIL",
    "순창군": "SUNCHANG",
    "고창군": "GOCHANG",
    "부안군": "BUAN",
    # ──────────────────────────────────────────────
    # Jeollanam-do (KR-46) — 5 si + 17 gun
    # ──────────────────────────────────────────────
    "목포시": "MOKPO",
    "여수시": "YEOSU",
    "순천시": "SUNCHEON",
    "나주시": "NAJU",
    "광양시": "GWANGYANG",
    "담양군": "DAMYANG",
    "곡성군": "GOKSEONG",
    "구례군": "GURYE",
    "고흥군": "GOHEUNG",
    "보성군": "BOSEONG",
    "화순군": "HWASUN",
    "장흥군": "JANGHEUNG",
    "강진군": "GANGJIN",
    "해남군": "HAENAM",
    "영암군": "YEONGAM",
    "무안군": "MUAN",
    "함평군": "HAMPYEONG",
    "영광군 (전라남도)": "YEONGGWANG",
    "장성군": "JANGSEONG",
    "완도군": "WANDO",
    "진도군": "JINDO",
    "신안군": "SINAN",
    # ──────────────────────────────────────────────
    # Gyeongsangnam-do (KR-48) — 8 si + 10 gun
    # ──────────────────────────────────────────────
    "창원시": "CHANGWON",
    "진주시": "JINJU",
    "통영시": "TONGYEONG",
    "사천시": "SACHEON",
    "김해시": "GIMHAE",
    "밀양시": "MIRYANG",
    "거제시": "GEOJE",
    "양산시": "YANGSAN",
    "의령군": "UIRYEONG",
    "함안군": "HAMAN",
    "창녕군": "CHANGNYEONG",
    "고성군 (경상남도)": "GOSEONG-GYEONGNAM",
    "남해군": "NAMHAE",
    "하동군": "HADONG",
    "산청군": "SANCHEONG",
    "함양군": "HAMYANG",
    "거창군": "GEOCHANG",
    "합천군": "HAPCHEON",
    # ──────────────────────────────────────────────
    # Jeju (KR-50) — 2 si
    # ──────────────────────────────────────────────
    "제주시": "JEJU",
    "서귀포시": "SEOGWIPO",
}


def detect_province(texts: list[str]) -> ProvinceReference | None:
    haystack = "\n".join(texts)
    for province in PROVINCES:
        if (
            province.name_ko in haystack
            or re.search(
                rf"\b{re.escape(province.name_en.replace('-do', ''))}\b",
                haystack,
                re.IGNORECASE,
            )
        ):
            return province
    return None


def find_province(prefecture_id: str) -> ProvinceReference | None:
    for province in PROVINCES:
        if province.prefecture_id == prefecture_id:
            return province
    return None


def validate_target_coverage(targets_dir: "Path | None" = None) -> list[str]:
    """Return municipality names from MUNICIPALITY_EN_MAP not found in any target file.

    Loads all 17 target JSON files from *targets_dir* (defaults to
    ``crawling/KR/targets/``), collects every title string, and compares
    against the keys of :data:`MUNICIPALITY_EN_MAP`.

    Returns a list of missing municipality names (empty if coverage is complete).
    """
    import json

    if targets_dir is None:
        targets_dir = Path(__file__).parent / "targets"
    else:
        targets_dir = Path(targets_dir)

    all_titles: set[str] = set()
    for target_file in sorted(targets_dir.glob("*_municipalities_ko.json")):
        try:
            payload = json.loads(target_file.read_text(encoding="utf-8"))
            for item in payload:
                if isinstance(item, str):
                    all_titles.add(item)
                elif isinstance(item, dict) and "title" in item:
                    all_titles.add(item["title"])
        except Exception as e:
            print(f"Warning: Could not load target file {target_file}: {e}")

    missing = [name for name in MUNICIPALITY_EN_MAP if name not in all_titles]
    if missing:
        print(
            f"Target coverage gap: {len(missing)} municipalities "
            f"in MUNICIPALITY_EN_MAP not found in target files."
        )
    return missing
