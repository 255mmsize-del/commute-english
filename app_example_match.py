"""표현이 예문에 실제로 들어 있는지 판별(활용형·불규칙 동사·축약형 허용). app_fetch·app_examples_gen 공용."""

from __future__ import annotations

import re

IRR = {"be":"am|is|are|was|were|been|being|be","have":"has|had|having|have","go":"goes|went|gone|going|go","do":"does|did|done|doing|do",
       "take":"takes|took|taken|taking|take","make":"makes|made|making|make","get":"gets|got|gotten|getting|get","come":"comes|came|coming|come",
       "give":"gives|gave|given|giving|give","keep":"keeps|kept|keeping|keep","bring":"brings|brought|bringing|bring","catch":"catches|caught|catching|catch",
       "run":"runs|ran|running|run","put":"puts|putting|put","set":"sets|setting|set","think":"thinks|thought|thinking|think","stick":"sticks|stuck|sticking|stick",
       "find":"finds|found|finding|find","hold":"holds|held|holding|hold","fall":"falls|fell|fallen|falling|fall","break":"breaks|broke|broken|breaking|break",
       "see":"sees|saw|seen|seeing|see","tell":"tells|told|telling|tell","say":"says|said|saying|say","feel":"feels|felt|feeling|feel","leave":"leaves|left|leaving|leave",
       "let":"lets|letting|let","cut":"cuts|cutting|cut","hit":"hits|hitting|hit","buy":"buys|bought|buying|buy","pay":"pays|paid|paying|pay","lose":"loses|lost|losing|lose",
       "sell":"sells|sold|selling|sell","speak":"speaks|spoke|spoken|speaking|speak","stand":"stands|stood|standing|stand","throw":"throws|threw|thrown|throwing|throw",
       "wear":"wears|wore|worn|wearing|wear","win":"wins|won|winning|win","write":"writes|wrote|written|writing|write","drive":"drives|drove|driven|driving|drive",
       "eat":"eats|ate|eaten|eating|eat","grow":"grows|grew|grown|growing|grow","know":"knows|knew|known|knowing|know","blow":"blows|blew|blown|blowing|blow",
       "draw":"draws|drew|drawn|drawing|draw","fly":"flies|flew|flown|flying|fly","hang":"hangs|hung|hanging|hang","lay":"lays|laid|laying|lay","lie":"lies|lay|lied|lying|lie",
       "mean":"means|meant|meaning|mean","meet":"meets|met|meeting|meet","ride":"rides|rode|ridden|riding|ride","rise":"rises|rose|risen|rising|rise",
       "shake":"shakes|shook|shaken|shaking|shake","sit":"sits|sat|sitting|sit","sleep":"sleeps|slept|sleeping|sleep","spend":"spends|spent|spending|spend",
       "swear":"swears|swore|sworn|swearing|swear","teach":"teaches|taught|teaching|teach","tear":"tears|tore|torn|tearing|tear","wake":"wakes|woke|woken|waking|wake",
       "hide":"hides|hid|hidden|hiding|hide","bite":"bites|bit|bitten|biting|bite","dig":"digs|dug|digging|dig","feed":"feeds|fed|feeding|feed","fight":"fights|fought|fighting|fight",
       "freeze":"freezes|froze|frozen|freezing|freeze","lead":"leads|led|leading|lead","light":"lights|lit|lighting|light","seek":"seeks|sought|seeking|seek",
       "shoot":"shoots|shot|shooting|shoot","sink":"sinks|sank|sunk|sinking|sink","slide":"slides|slid|sliding|slide","spin":"spins|spun|spinning|spin","steal":"steals|stole|stolen|stealing|steal",
       "strike":"strikes|struck|striking|strike","swing":"swings|swung|swinging|swing","build":"builds|built|building|build","send":"sends|sent|sending|send","bend":"bends|bent|bending|bend",
       "lend":"lends|lent|lending|lend","deal":"deals|dealt|dealing|deal","forget":"forgets|forgot|forgotten|forgetting|forget","understand":"understands|understood|understanding|understand",
       "i'm":"i'm|i am","you're":"you're|you are","it's":"it's|it is","don't":"don't|do not|doesn't|didn't","can't":"can't|cannot|couldn't","won't":"won't|will not"}
STOP = {"sb", "sth", "someone", "something", "one's", "oneself", "somebody", "~", "a", "an", "the"}


def tokens(en: str) -> list[str]:
    en = en.lower().replace("’", "'")
    en = re.sub(r"\(.*?\)|\[.*?\]|\+.*$|[~…]", " ", en).split("/")[0]
    toks = [re.sub(r"[^a-z']", "", t).strip("'") for t in en.split()]
    return [t for t in toks if t and t not in STOP and re.search(r"[a-z]", t)]


def tokre(t: str) -> str:
    if t == "be":   # I'm / you're / it's 같은 축약형도 be 로 인정
        return r"(?:(?<![a-z])(?:%s)|['’](?:m|re|s))(?![a-z])" % IRR["be"]
    if t in IRR:
        return r"(?<![a-z])(?:%s)(?![a-z])" % IRR[t]
    stem = t
    if len(t) > 4:
        stem = re.sub(r"(e|y|ies|es|s|ed|ing)$", "", t)
    return r"(?<![a-z])" + re.escape(stem).replace("'", "['’]") + r"[a-z'’]*(?![a-z])"


def matcher(en: str):
    """표현의 핵심 단어가 모두 들어 있으면 True 를 돌려주는 함수(핵심 단어가 없으면 None)."""
    ts = tokens(en)
    if not ts:
        return None
    res = [re.compile(tokre(t), re.I) for t in ts]
    return lambda s: all(r.search(s.replace("’", "'")) for r in res)


def example_lines(en: str, ex: list) -> list[list[str]]:
    """예문(대화 포함)에서 표현이 들어간 문장을 [영어, 한국어] 로 뽑는다. 대화는 줄 단위로 나눈다."""
    m = matcher(en)
    if m is None:
        return []
    out = []
    for e, k in ex:
        el, kl = e.split("\n"), str(k).split("\n")
        for i, line in enumerate(el):
            s = re.sub(r"^[AB]:\s*", "", line).strip()
            if not s or re.search(r"[가-힣]", s) or not m(s):
                continue
            ko = kl[i] if len(kl) == len(el) else (k if len(el) == 1 else "")
            out.append([s, re.sub(r"^[AB]:\s*", "", ko).strip()])
    return out


def qa_pairs(en: str, ex: list) -> list[list[str]]:
    """대화 예문에서 표현이 들어간 질문·답변 한 쌍을 ["A: …\nB: …", "A: …\nB: …"] 로 뽑는다."""
    m = matcher(en)
    if m is None:
        return []
    out = []
    for e, k in ex:
        el, kl = e.split("\n"), str(k).split("\n")
        if len(el) < 2 or len(kl) != len(el):
            continue
        body = [re.sub(r"^[AB]:\s*", "", x).strip() for x in el]
        kbody = [re.sub(r"^[AB]:\s*", "", x).strip() for x in kl]
        for i, s in enumerate(body):
            if not m(s):
                continue
            # 질문(?로 끝남) + 바로 다음 답변 한 쌍. 표현은 질문이나 답변 어느 쪽에 있어도 됨
            for j in (i - 1, i):
                if 0 <= j < len(body) - 1 and body[j].endswith("?") and not body[j + 1].endswith("?"):
                    out.append([f"A: {body[j]}\nB: {body[j + 1]}", f"A: {kbody[j]}\nB: {kbody[j + 1]}"])
                    break
            break
    return out
