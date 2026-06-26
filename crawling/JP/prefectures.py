"""
일본 도도부현 참조 데이터.

이 파일은 도시 정규화에서 사용하는 도도부현 조회와 판별 도우미를 담당한다.
"""

from __future__ import annotations

import re
from typing import Final

from crawling.JP.models import PrefectureReference


PREFECTURES: Final[tuple[PrefectureReference, ...]] = (
    PrefectureReference("JP-01", "홋카이도", "北海道", "Hokkaido", "Hokkaido"),
    PrefectureReference("JP-02", "아오모리현", "青森県", "Aomori", "Tohoku"),
    PrefectureReference("JP-03", "이와테현", "岩手県", "Iwate", "Tohoku"),
    PrefectureReference("JP-04", "미야기현", "宮城県", "Miyagi", "Tohoku"),
    PrefectureReference("JP-05", "아키타현", "秋田県", "Akita", "Tohoku"),
    PrefectureReference("JP-06", "야마가타현", "山形県", "Yamagata", "Tohoku"),
    PrefectureReference("JP-07", "후쿠시마현", "福島県", "Fukushima", "Tohoku"),
    PrefectureReference("JP-08", "이바라키현", "茨城県", "Ibaraki", "Kanto"),
    PrefectureReference("JP-09", "도치기현", "栃木県", "Tochigi", "Kanto"),
    PrefectureReference("JP-10", "군마현", "群馬県", "Gunma", "Kanto"),
    PrefectureReference("JP-11", "사이타마현", "埼玉県", "Saitama", "Kanto"),
    PrefectureReference("JP-12", "지바현", "千葉県", "Chiba", "Kanto"),
    PrefectureReference("JP-13", "도쿄도", "東京都", "Tokyo", "Kanto"),
    PrefectureReference("JP-14", "가나가와현", "神奈川県", "Kanagawa", "Kanto"),
    PrefectureReference("JP-15", "니가타현", "新潟県", "Niigata", "Chubu"),
    PrefectureReference("JP-16", "도야마현", "富山県", "Toyama", "Chubu"),
    PrefectureReference("JP-17", "이시카와현", "石川県", "Ishikawa", "Chubu"),
    PrefectureReference("JP-18", "후쿠이현", "福井県", "Fukui", "Chubu"),
    PrefectureReference("JP-19", "야마나시현", "山梨県", "Yamanashi", "Chubu"),
    PrefectureReference("JP-20", "나가노현", "長野県", "Nagano", "Chubu"),
    PrefectureReference("JP-21", "기후현", "岐阜県", "Gifu", "Chubu"),
    PrefectureReference("JP-22", "시즈오카현", "静岡県", "Shizuoka", "Chubu"),
    PrefectureReference("JP-23", "아이치현", "愛知県", "Aichi", "Chubu"),
    PrefectureReference("JP-24", "미에현", "三重県", "Mie", "Kansai"),
    PrefectureReference("JP-25", "시가현", "滋賀県", "Shiga", "Kansai"),
    PrefectureReference("JP-26", "교토부", "京都府", "Kyoto", "Kansai"),
    PrefectureReference("JP-27", "오사카부", "大阪府", "Osaka", "Kansai"),
    PrefectureReference("JP-28", "효고현", "兵庫県", "Hyogo", "Kansai"),
    PrefectureReference("JP-29", "나라현", "奈良県", "Nara", "Kansai"),
    PrefectureReference("JP-30", "와카야마현", "和歌山県", "Wakayama", "Kansai"),
    PrefectureReference("JP-31", "돗토리현", "鳥取県", "Tottori", "Chugoku"),
    PrefectureReference("JP-32", "시마네현", "島根県", "Shimane", "Chugoku"),
    PrefectureReference("JP-33", "오카야마현", "岡山県", "Okayama", "Chugoku"),
    PrefectureReference("JP-34", "히로시마현", "広島県", "Hiroshima", "Chugoku"),
    PrefectureReference("JP-35", "야마구치현", "山口県", "Yamaguchi", "Chugoku"),
    PrefectureReference("JP-36", "도쿠시마현", "徳島県", "Tokushima", "Shikoku"),
    PrefectureReference("JP-37", "가가와현", "香川県", "Kagawa", "Shikoku"),
    PrefectureReference("JP-38", "에히메현", "愛媛県", "Ehime", "Shikoku"),
    PrefectureReference("JP-39", "고치현", "高知県", "Kochi", "Shikoku"),
    PrefectureReference("JP-40", "후쿠오카현", "福岡県", "Fukuoka", "Kyushu"),
    PrefectureReference("JP-41", "사가현", "佐賀県", "Saga", "Kyushu"),
    PrefectureReference("JP-42", "나가사키현", "長崎県", "Nagasaki", "Kyushu"),
    PrefectureReference("JP-43", "구마모토현", "熊本県", "Kumamoto", "Kyushu"),
    PrefectureReference("JP-44", "오이타현", "大分県", "Oita", "Kyushu"),
    PrefectureReference("JP-45", "미야자키현", "宮崎県", "Miyazaki", "Kyushu"),
    PrefectureReference("JP-46", "가고시마현", "鹿児島県", "Kagoshima", "Kyushu"),
    PrefectureReference("JP-47", "오키나와현", "沖縄県", "Okinawa", "Kyushu"),
)


def detect_prefecture(texts: list[str]) -> PrefectureReference | None:
    haystack = "\n".join(texts)
    for prefecture in PREFECTURES:
        if (
            prefecture.name_ko in haystack
            or prefecture.name_ja in haystack
            or re.search(rf"\b{re.escape(prefecture.name_en)}\b", haystack, re.IGNORECASE)
        ):
            return prefecture
    return None


def find_prefecture(prefecture_id: str) -> PrefectureReference | None:
    for prefecture in PREFECTURES:
        if prefecture.prefecture_id == prefecture_id:
            return prefecture
    return None


# 파일 이력
# 2026-06-04: CLI 모듈에서 도도부현 참조 조회를 분리했다.

