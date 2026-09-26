"""
Modelin ürettiği özel syntax'ları yakalar:
  - <CALL_TOOL: eklenti_adi sorgu |>   -> bir eklentiyi çağırma isteği
  - <SAVE_MEMORY: özet_bilgi |>        -> kalıcı hafızaya yazma isteği (yan etki, geri dönüş beklemez)

İkisi de stringin İÇİNDE herhangi bir yerde aranır - model normal cevabıyla
birlikte, aynı çıktıda üretebilir.
"""
import re
from dataclasses import dataclass
from typing import Optional

TOOL_PATTERN = re.compile(r"<CALL_TOOL:\s*(\w+)\s+(.*?)\s*\|>", re.DOTALL)
SAVE_PATTERN = re.compile(r"<SAVE_MEMORY:\s*(.*?)\s*\|>", re.DOTALL)


@dataclass
class ParsedResponse:
    narration: str
    tool_name: Optional[str]
    query: Optional[str]
    is_final: bool
    memory_to_save: Optional[str] = None


def parse_model_output(raw_output: str) -> ParsedResponse:
    # Önce SAVE_MEMORY'yi ayıkla ve metinden çıkar - kalan metin normal
    # narration/tool-call ayrıştırmasına o şekilde girsin.
    memory_to_save = None
    save_match = SAVE_PATTERN.search(raw_output)
    if save_match:
        memory_to_save = save_match.group(1).strip()
        raw_output = raw_output[: save_match.start()] + raw_output[save_match.end():]

    match = TOOL_PATTERN.search(raw_output)
    if match:
        narration = raw_output[: match.start()].strip()
        return ParsedResponse(
            narration=narration,
            tool_name=match.group(1),
            query=match.group(2).strip(),
            is_final=False,
            memory_to_save=memory_to_save,
        )

    return ParsedResponse(
        narration=raw_output.strip(),
        tool_name=None,
        query=None,
        is_final=True,
        memory_to_save=memory_to_save,
    )