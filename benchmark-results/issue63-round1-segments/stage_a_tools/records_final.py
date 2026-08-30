"""final_round1_10_4of13 records.

The final submission's per-query task types diverge from the official test-round
list (p1-3 extra as qa; p1-4 kis vs trake; p1-17 qa vs kis; p1-18 kis vs trake;
p1-19 kis vs qa; p1-22 kis vs qa). No Round-1-specific query text exists locally,
so ranges are proposed from observed visual segments only, with low/medium
confidence. Official test-round text is attached as REFERENCE ONLY where IDs align.
"""

FINAL = "final_round1_10_4of13"

R = []


def rec(qid, qtype, video, anchors, ranges, conf, why, conflicts, note=None):
    R.append(dict(submission=FINAL, qid=qid, qtype=qtype, video=video, anchors=anchors,
                  ranges=ranges, confidence=conf, reasoning=why, conflicts=conflicts,
                  note=note, text_status="round1_text_unavailable"))


rec("p1-1", "kis", "L30_V046", [6648], [(254, 274.4)], "low",
    "TuoitreTV street-fitness piece. Anchor 265.92s = seated stretch closeup with 'Tac gia: THANH THI' caption; wide group-stretch shot 255.9-261.9; content montage ends before logo card ~275.9. Proposed range = final exercise montage [~254, 274.4].",
    "Round-1 query text unavailable; official test-round P1-01 (spacecraft) does not match this content - type/content conflict recorded, range is visual-segment only.")
rec("p1-2", "kis", "L28_V018", [3032], [(105, 128)], "low",
    "HTV 'Den va o lai - Tap 18' Mekong documentary. Anchor 121.28s sits inside a satellite-map graphic (Kenh T3/T4/T5, Kenh Ha Tien - Rach Gia) spanning ~105-128s, between canal aerials (<=101s) and bridge footage (>=129s). Proposed range = the map segment.",
    "Round-1 text unavailable; official test-round P1-02 (village with dog cubs) does not match. Map start/end estimated from 10s grid.")
rec("p1-3", "qa", "L21_V023", [26042], [(848, 940), (856, 874)], "low",
    "HTV9 news block. Banded (bamboo) shark story ~[848,940]: pufferfish 848, shark weighed on scale (ANCHOR 868.07), closeups 878-898, tub 908-938; interview Tiensy Jode Rummer ~918. Submitted QA answer '5'. Secondary tight range = weighing shot [856,874].",
    "p1-3 does NOT exist in the official 24-query test-round list (extra file). Query text unknown; answer '5' unverified (possibly shark count).")
rec("p1-4", "kis", "L22_V021", [19738], [(645, 715)], "low",
    "HTV7 news. London Zoo lion-cubs weigh-in: studio intro w/ inset ~647.9, zoo footage (cubs on LONDON ZOO sign at ANCHOR 657.93) 655-712, keeper interview 667-707, back to studio ~717.9. Proposed range [645,715].",
    "TYPE CONFLICT: official test-round P1-04 is TRAKE (net casting) but final submits KIS; content (lions) matches neither. Round-1 text unavailable.")
rec("p1-5", "kis", "L26_V035", [5069], [(185, 265)], "low",
    "HTV 'Mon Ngon Chua Lanh' cooking show. Squid stir-fry: prep 112-182, wok cooking from ~185 (squid 192.8), ANCHOR 202.76 = adding snow peas to pan, stir-fry through ~262, plated dish 292.8. Proposed range = cooking-the-dish [185,265].",
    "Round-1 text unavailable; official test-round P1-05 (two women feeding animals) does not match.")
rec("p1-6", "kis", "L22_V023", [18180], [(705, 770)], "low",
    "HTV7 news. Botswana 2492-carat diamond story: presenter inset ~707, president viewing diamond at ANCHOR 727.2, mine/Lucara diamond 747-767, truck-fire item by ~777. Proposed range [705,770].",
    "Round-1 text unavailable; official test-round P1-06 (fresh rolls plating) does not match.")
rec("p1-7", "kis", "L26_V041", [3656], [(125, 215)], "low",
    "HTV 'Mon Ngon Moi Ngay'. Vegetable blanching: prep 106-136, carrot flowers in boiling water at ANCHOR 146.24, blanching cauliflower/zucchini 156-206, plating 206-216. Proposed range [125,215].",
    "Round-1 text unavailable; official test-round P1-07 (forest bird) does not match. Row-3 answer 6797 jumps to a different scene (noted).")
rec("p1-8", "kis", "L26_V171", [5455], [(205, 260)], "low",
    "HTV 'Mon Ngon Moi Ngay'. Steamed egg dish: egg mixing 118-208, plate into steamer at ANCHOR 218.2, steamed dish + toppings 228-258. Proposed range = steaming phase [205,260].",
    "Round-1 text unavailable; official test-round P1-08 (Japanese festival octopus girl) does not match. DUPLICATE: p1-14 submits identical answers (same video+frames).")
rec("p1-9", "qa", "L21_V003", [26220], [(1030, 1075)], "low",
    "HTV9 news. Amphicar story: intro ~1028, ANCHOR 1048.8 = amphicar driving on water under bridge, amphicars on canal 1068, presenter 1078. Proposed range [1030,1075]. Submitted QA answer '2,15'.",
    "Round-1 text unavailable; official test-round P1-09 is KIS (pineapple harvest) - type+content conflict. Answer '2,15' unverified.")
rec("p1-10", "kis", "L29_V013", [11278], [(440, 525)], "low",
    "'Mekong Vietnam' grape-farm visit. ANCHOR 451.12 = cutting green grapes with scissors; basket 461; walking with basket 471-511; tasting 531-551. Proposed range = harvest segment [440,525].",
    "Round-1 text unavailable; official test-round P1-10 (handpan trio) does not match.")
rec("p1-11", "kis", "L23_V021", [6972], [(250, 300)], "low",
    "HTV The Thao cycling race. Sprint finish at DICH arch: aerial peloton 218-248, finish-line sprints 258-298 (ANCHOR 278.88 = three riders sprinting), replays 298-368. Proposed range = finish sprint [250,300].",
    "Round-1 text unavailable; official test-round P1-11 (shadow portrait art) does not match.")
rec("p1-12", "kis", "L22_V001", [3155], [(100, 113)], "low",
    "HTV7 60s news. Fuel-price story: ANCHOR 105.17 = gas-station price graphic (RON95/E5/diesel/oil table); presenter 115-125; flood stories from ~135. Proposed range = price item [100,113].",
    "Round-1 text unavailable; official test-round P1-12 (doughnut decorating) does not match.")
rec("p1-13", "kis", "L29_V021", [6230], [(235, 285)], "low",
    "'Duna Mekong' night-fishing episode. ANCHOR 249.2 = dawn blue-hour wide of boat; night fishing 149-239; sunrise 259-289; day net casting 289-319; interviews 329-349. Proposed range = night-to-dawn transition [235,285].",
    "Round-1 text unavailable; official test-round P1-13 (camera cleaning) does not match.")
rec("p1-14", "kis", "L26_V171", [5455], [(205, 260)], "low",
    "Identical submitted answer to p1-8 (L26_V171 @5455...). Same steamed-egg segment; proposed range identical [205,260].",
    "DUPLICATE-ANSWER CONFLICT: same video+frames submitted for two different queries (p1-8 and p1-14) in one submission; at most one can be correct. Round-1 text unavailable.")
rec("p1-15", "qa", "L21_V010", [19430], [(770, 800)], "low",
    "HTV9 60s news. Japan earthquake story: ANCHOR 777.2 = seismic-intensity map graphic (Japan Meteorological Agency), warning maps (Shikoku/Ehime/Oita/Kochi/Miyazaki/Kagoshima) 787-797, next item ~807. Proposed range [770,800]. Submitted QA answer '12'.",
    "Round-1 text unavailable; official test-round P1-15 (FANA commune QA) does not match. Answer '12' unverified.")
rec("p1-16", "trake", "L24_V024", [9785, 10135, 10191],
    [(285, 390), (320, 332), (336, 341), (338, 348)], "low",
    "HTV The Thao lion dance on poles (white lion). Continuous performance ~286-385+. E1 anchor 326.17 = lion on pole wide; E2 anchor 337.83 = closeup on pole; E3 anchor 339.7 = gong-strike closeup during performance. Per-event windows are mechanical; continuous range [285,390] proposed (end uncertain, performance continues past window).",
    "Official test-round P1-16 is a 4-event snake/lion query; final submits only 3 anchors and Round-1 event definitions are unknown. Event-to-range mapping is not semantic here.")
rec("p1-17", "qa", "L22_V008", [5638], [(220, 250)], "medium",
    "HTV7 news. Landslide story: ANCHOR 225.52 = Tua Pua pass landslide blocking road (chyron 'BINH THUAN: SAT LO DEO TA PUA GAY ACH TAC GIAO THONG'); mud shots 235-245; Lai Chau boulder item ~255. Submitted QA answers 'Ta Pua' / 'Deo Ta Pua' MATCH the visible chyron. Proposed range [220,250].",
    "TYPE CONFLICT: official test-round P1-17 is KIS (hospital charity) but final submits QA; however the QA answer aligns with the on-screen text, so this is likely a genuine Round-1 QA item.")
rec("p1-18", "kis", "L26_V389", [5795], [(225, 240)], "low",
    "HTV 'Mon Ngon Moi Ngay'. Noodle dish: wok frying 161-211, ANCHOR 231.8 = noodles boiling in pot (chopsticks lifting), ladling into bowl 241-251, finished bowl 271-281. Proposed range = noodles-in-pot [225,240].",
    "TYPE CONFLICT: official test-round P1-18 is TRAKE (mushroom dish events) but final submits KIS. Round-1 text unavailable.")
rec("p1-19", "kis", "L24_V035", [13824], [(385, 600)], "low",
    "HTV The Thao night lion dance on poles (yellow lion). Performance ~385-600: pole jumps (ANCHOR 460.8 mid-leap), wide shots 540-560, finale closeups ~570-590. Proposed continuous range [385,600]; both boundaries beyond the inspected window (start visible ~385, end estimated).",
    "TYPE CONFLICT: official test-round P1-19 is QA (temple couplets) but final submits KIS. Round-1 text unavailable; long-range boundaries low confidence.")
rec("p1-20", "kis", "L21_V026", [7454], [(245, 262)], "low",
    "HTV9 morning news. Quang Ngai landslide/disaster story: ANCHOR 248.47 = umbrella shot with chyron 'BAC QUANG: 3 NGUOI THUONG VONG, THIET HAI 1,1 TY DONG DO THIEN TAI'; house interior 258-268; presenter 278. Proposed range [245,262].",
    "Round-1 text unavailable; official test-round P1-20 (panna cotta) does not match.")
rec("p1-21", "kis", "L22_V011", [15244], [(500, 545)], "low",
    "HTV7 60s. Food montage: ANCHOR 508.13 = fried food closeup (priority-voucher chyron), shrimp dish 518, dessert 528, Thanh Hoa shrimp-festival banner 538, cooking-hands 548-558. Proposed range = food montage [500,545].",
    "Round-1 text unavailable; official test-round P1-21 (Lausanne robot birds) does not match.")
rec("p1-22", "kis", "L25_V041", [17152], [(645, 692)], "low",
    "'Thay Mien' English grammar lecture (gerund vs to-infinitive): forget 586-636, remember 646-686 (ANCHOR 686.08 'remember to call me...'), regret 696-756, stop 766+. Proposed range = 'remember' section [645,692].",
    "TYPE CONFLICT: official test-round P1-22 is QA (recipe title) but final submits KIS. Round-1 text unavailable.")
rec("p1-23", "kis", "L25_V060", [26533], [(1050, 1160)], "low",
    "'Thay Mien' geography lecture (labor-force structure). ANCHOR 1061.32 = slide 'Van de viec lam va huong giai quyet'; adjacent slides 1041-1165 within window; whole lecture is continuous. Proposed range = anchor-slide section [1050,1160].",
    "Round-1 text unavailable; official test-round P1-23 (Jaws shark town) does not match.")
rec("p1-24", "kis", "L29_V001", [9100], [(350, 380), (340, 430)], "low",
    "'Duna Mekong' water-hyacinth weaving village. ANCHOR 364.0 = woven-bag closeup with red flowers; product closeups 354-374; showroom 374-424; workshop 434; interviews 444-464. Proposed primary = product-closeup shot [350,380]; alt wider showcase [340,430].",
    "Round-1 text unavailable; official test-round P1-24 (top-down 3 riders) does not match.")
rec("p1-25", "kis", "L30_V003", [6611], [(260, 300)], "low",
    "TuoitreTV student story. ANCHOR 264.44 = boy presenting at 'LEADERSHIP STEAM FAIR 2021' podium; stage presentations 254-294; kids group 304-314; medals table 334. Proposed range = STEAM-fair presentation [260,300].",
    "Round-1 text unavailable; official test-round P1-25 (drone cyclist overtake) does not match.")
