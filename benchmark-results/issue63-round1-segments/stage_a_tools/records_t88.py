"""testing88_submission633 records (matches official test-round query list)."""

T88 = "testing88_submission633"

R = []


def rec(qid, qtype, video, anchors, ranges, conf, why, conflicts, note=None, tstat="official_test_round_p1"):
    R.append(dict(submission=T88, qid=qid, qtype=qtype, video=video, anchors=anchors,
                  ranges=ranges, confidence=conf, reasoning=why, conflicts=conflicts,
                  note=note, text_status=tstat))


rec("p1-1", "kis", "L21_V015", [25283], [(840, 905)], "low",
    "Anchor 842.77s = HTV9 presenter inset of SpaceX Starship launch failure; then rocket on pad ~862s, Earth from orbit 872-892s, Starlink satellite ~892s, presenter ~903s. Continuous space/rocket story bracket [840,905]. The official KIS asks for an intro scene with 4 people in black suits + polar-light research; that scene was NOT observed within +/-100s of the anchor.",
    "Anchor content (rocket-explosion inset) does not show the queried '4 astronauts in black / polar light' scene; range is story-level only.",
    note="Minh: locate the 4-astronaut scene in L21_V015 if it exists.")

rec("p1-2", "kis", "L21_V029", [10908], [(375, 425)], "medium",
    "Official query = Southern locality with ~3-6 rare tiger/panther cubs. Anchor 363.6s = story intro (adult Bengal cats, chyron 'DONG NAI: 2 meo Bengal quy hiem sinh 3 con tai khu du lich Von Xoai'); cubs-on-grass shots run ~375-425s (3 cubs walking). Range covers cubs footage; story intro [~358,375] is an alternative inclusion.",
    "Anchor sits on the adult-cat intro shot, not the cubs shots; boundary estimated from 10s grid.",
    note="Minh: decide whether the story intro counts.")

rec("p1-4", "trake", "L26_V194", [4707, 5139, 5427, 5865],
    [(188, 193), (205, 208), (217, 220), (233, 236)], "low",
    "All four anchors land inside an HTV 'Mon Ngon Moi Ngay' cooking segment (asparagus tempura): E1 188.28s = asparagus in bowl with flour; E2 205.56s = lid on bowl; E3 217.08s = deep-frying in oil; E4 234.6s = frying with chopsticks. NO net-casting content exists in this window; official P1-04 events (net casting) cannot be mapped onto this footage.",
    "MAJOR: submitted video appears unrelated to official P1-04 net-casting query. Ranges are mechanical windows around anchors, not semantic events.",
    tstat="official_text_unmappable")

rec("p1-5", "kis", "L27_V014", [7297], [(280, 335)], "medium",
    "Strong visual match: official query (OCR-garbled 'cho do an' = feeding goats; woman in white tee with red garment over shoulder + older woman in striped long sleeves; corrugated-roof barn, wooden fences, animal rows) matches anchor scene exactly ('Trai nghiem cho de an'). Feeding ~280-335s; bottle-feeding kid goat ~355-365 adjacent but distinct.",
    "End boundary estimated from 10s grid; milking starts ~370 (different activity).",
    note="Minh: decide whether bottle-feeding (~355-365) belongs in range.")

rec("p1-6", "kis", "L26_V056", [6300], [(245, 295)], "medium",
    "Strong match: query = opening scene, fresh rice-paper rolls with greens+tofu placed on tray decorated with purple leaves and yellow-white pansies. Anchor 252.0s = hands arranging purple roll on flower-decorated tray; plated closeups through ~292s. Rolling ~202-242, sauce ~152-192 are earlier phases.",
    "Start boundary between 'rolling' and 'plating' estimated; query says the clip BEGINS with the plating scene.",
    note=None)

rec("p1-7", "kis", "L29_V023", [10915], [(433, 441), (425, 455)], "medium",
    "Strong match: query bird = black-blue glossy head, plain brown-red body/wings, bright red eyes, on leaf-litter forest floor. Anchor 436.6s = exactly this bird (ground closeup, U Minh episode). Primary = bird shot [433,441]; wider alt [425,455] includes adjacent black-stork shot.",
    "Bird shot short; exact in/out frames need frame-accurate pass. Second range optional.",
    note="Minh: choose tight shot range vs wider story range.")

rec("p1-8", "kis", "L22_V030", [18327], [(730, 737), (700, 740)], "medium",
    "Strong match: query = woman at Japanese food festival with red octopus/squid at chest + paper bag in hand. Anchor 733.08s = girl holding red octopus-shaped item at BENTO Fest street-food stall. Primary = octopus shot [730,737]; wider [700,740] = festival-food story (okonomiyaki 713-723).",
    "Octopus shot is very short (~5-8s); story continues into unrelated fire item ~743.",
    note=None)

rec("p1-9", "kis", "L27_V013", [5050], [(195, 245)], "medium",
    "Strong match after OCR correction: official 'ban gio dua / thu hoach dua' is almost certainly PINEAPPLE (dua). Anchor 202.0s = two women (pink shirt + checkered scarf; older in purple) with yellow basket of pineapples, blue boat behind - matches query structure exactly. Peeling 232-242; host holds pineapple 192.",
    "Official capture text OCR-garbled (dua vs dua); match is structural+visual.",
    note="Minh: confirm dua reading; decide start (~192 host vs ~195 women+basket).")

rec("p1-10", "kis", "L30_V017", [2986], [(115, 125), (100, 140)], "medium",
    "Strong match: query = three players (2 women + 1 man) playing handpans, one in WHITE centered between two in BLACK, bookshelves behind. Anchor 119.44s = exactly this trio (TuoitreTV handpan story). Primary = trio shot [115,125]; wider [100,140] adds adjacent solo/closeup shots of same session.",
    "Trio shot brief; adjacent shots same location/different framing - Minh decides inclusiveness.",
    note=None)

rec("p1-11", "kis", "L30_V057", [3082], [(118, 135), (190, 225)], "medium",
    "Strong match: query = man in black cap + white English-text tee arranging cut wood on a box, side light casting a suited-man portrait shadow on wall. Anchor 123.28s = exactly this shadow-art shot. The demonstration appears TWICE: [~118,135] (anchor) and [~190,225] (wide + 'Tac gia: Minh Hung' ~213). Interview shots ~143-183 sit between.",
    "Two separated ranges proposed per issue's multiple-range allowance.",
    note=None)

rec("p1-12", "kis", "L26_V200", [4480], [(172, 272)], "medium",
    "Strong match: query = white ceramic plate on wooden tray beside scale with 2 dough balls + small plate of cut banana and brown spoon; then chef decorates 2 fried doughnuts: chocolate drizzle, banana slices, peanut candy. Anchor 179.2s = exactly the plate-on-tray setup. Decorating ~185-270 (chocolate 189, banana+strawberry 199-259, finished 269).",
    "Query does not mention strawberries but frame shows them; same scene assumed.",
    note=None)

rec("p1-13", "kis", "L30_V095", [2672], [(100, 112), (150, 205)], "medium",
    "Good match: query = camera cleaning: disassemble camera, lens removed onto pink/purple cloth, then lens cleaned with cloth. Anchor 106.88s = hands disassembling camera over cloth with lens elements. Cleaning shots ~150-205 (screwdriver + pink cloth ~147; lens wiped ~157-197).",
    "Anchor cloth reads green/pink vs query 'khan mau tim hong'; later shots show clearer pink cloth.",
    note=None)

rec("p1-14", "kis", "L21_V027", [26831], [(890, 940)], "medium",
    "Strong match: query = sand-sculpture festival, horizontal-cut sculpture of youth street sports (1 skater, 2 skateboarders), large arch + carved text, later 2 pink sand blocks. Anchor 894.37s = sand relief with figures (St. Petersburg festival chyron); David-bust 904; hand carving 'CAT' 924; pink smoke 934.",
    "Specific '2 pink sand blocks' not confirmed in 10s grid; anchor sculpture not clearly the sports scene.",
    note="Minh: verify sports-relief sculpture appears within [890,940].")

rec("p1-15", "qa", "L30_V072", [1745], [(55, 85)], "medium",
    "Video = 87s reader-submitted charity clip ('Cung Em Den Truong'). Anchor 69.8s = stage ceremony, children holding red gift bags. Range covers stage + children leaving with bags. Submitted QA answer: 'Giang Ly' / 'Xa nay co ten la Giang Ly'.",
    "Commune-name evidence (sign/voiceover) not verifiable from tiles; banner ~29.8s and audio need check.",
    note="Minh: zoom banner ~29.8s / listen; confirm 'Giang Ly'.")

rec("p1-16", "trake", "L24_V033", [15945, 16006, 16354, 16901],
    [(495, 533), (531, 545), (545, 562), (562, 595)], "low",
    "Lion dance (white/black) on poles at night, HTV The Thao. E1 531.5 = lion on structure near judges (spin/dismount ~495-533); E2 533.53 = lion crouched on ground by judges ('4 legs on ground'); E3 545.13 = lion lifted at judges table; E4 563.37 = lion at dragon structure, dragon head visible; performance ends before HTV card ~598.",
    "Semantics fit but exact first-instance boundaries need frame-accurate passes; 5s grid only brackets.",
    note=None)

rec("p1-17", "kis", "L30_V092", [2491], [(93, 108)], "medium",
    "Strong match: query = spring-2024 hospital charity; two men (pink + white shirts) flanking; four children (red/white/pink-dress/blue) receiving symbolic plaques; big medical-logo gift bag; red backdrop with spring slogans. Anchor 99.64s = exactly this ceremony ('Mung Xuan - benh vien tinh 2024', 'Cho 0 dong').",
    "'COVID orphans' banner text not read at tile size. Tight range; frame-accurate pass recommended.",
    note=None)

rec("p1-18", "trake", "L26_V072", [2466, 3133, 3420, 3800],
    [(95, 103), (120, 128), (139, 147), (163, 182)], "low",
    "Mushroom dish cooking. E1 98.64 = slicing white mushrooms (first slices ~96-101); E2 125.32 = slicing shiitake; E3 136.8 = MEO card + tofu, first cuts ~140-146; E4 anchor 152.0 = cutting cu nang, but official E4 = sauce poured + flames; oil/flame sequence ~163-182 (scallions 166.8, mushrooms into oil ~181), open flame not directly observed at 5s granularity.",
    "E4 anchor sits in a cutting shot, not the flame shot - anchor likely misaligned for E4; official text duplicates 'E2' label (preserved).",
    note="Minh: confirm flame moment for E4 (likely ~166-181).")

rec("p1-19", "qa", "L27_V010", [5535], [(215, 232)], "medium",
    "Strong match: anchor 221.4s = bronze bust flanked by couplet panels reading 'HONG NHAO PHAT OANH THIEN DIA / BAT KIEN GIANG KHAP QUI THAN' - one of the two queried couplets at Nguyen Trung Truc temple (Kien Giang). Submitted answer transcribes this couplet. Altar/portrait 241-291; possible second couplet on stone stele ~305-315 (unconfirmed).",
    "Second couplet evidence unconfirmed; answer text variants between rows preserved verbatim.",
    note="Minh: locate/confirm second couplet (possibly ~305-315).")

rec("p1-20", "kis", "L26_V004", [5400], [(214, 278)], "medium",
    "Strong match: query = white round plate with 1 panna cotta; hand adds 2 more glasses; each topped with white cream, red grape slices, mint; two edible flowers (red+yellow) beside. Anchor 216.0s = single-glass-on-plate moment with two flowers; two-glasses closeups 236-276; host tasting 226.",
    "The literal 'hand placing 2 more glasses' action not isolated in 10s grid (between 216-236).",
    note=None)

rec("p1-21", "kis", "L21_V004", [21690], [], "low",
    "BLOCKER: source video L21_V004.mp4 is NOT present in the local corpus (videos/L21 has V001-V019 and V021-V031; V004 and V020 absent). No range can be proposed without source media.",
    "Missing local source video. Do not invent truth; exclude unless file recovered.",
    tstat="official_text_unverifiable_locally")

rec("p1-22", "qa", "L30_V078", [1788], [(68, 78)], "low",
    "Anchor 71.52s = hands holding a printed recipe card (queried evidence: '200g thit noc xay'). Card text too small at tile resolution; submitted answer 'Nhan banh cuon' cannot be visually confirmed (video shows a charity baking event with cupcakes/cakes).",
    "Answer-vs-video consistency unresolved: card needs zoom/OCR; 'banh cuon' vs baked cakes is suspicious.",
    note="Minh: zoom recipe card ~71.5s; verify '200g thit noc xay' and title.")

rec("p1-23", "kis", "L22_V022", [16755], [(555, 645)], "medium",
    "Strong match: query = coastal town attracting curious tourists due to dangerous marine animal famous from Spielberg's 1975 film (Jaws). Anchor 558.5s = aerial coastline with chyron 'CANH BAO ... BIEN CO O MY: THU HUT DU KHACH HIEM KY'; lifeguard interview (Wellfleet, Massachusetts) ~618; great white shark mouth closeup ~638.5.",
    "Specific shark-hunt action not isolated; range = whole beach-warning story; end before studio ~645 estimated.",
    note=None)

rec("p1-24", "kis", "L23_V007", [3246], [(126, 142), (120, 160)], "medium",
    "Strong structural match: query = head-on top-down drone shot following riders; 3 riders in a straight line, same team. Anchor 129.84s = top-down shot of 3 single-file riders on gray road with palm tree. Wider alt [120,160] includes adjacent top-down shots (139.8, 149.8).",
    "Query's jersey colors (white/red/black tops) not verifiable at tile size; Minh should confirm colors.",
    note=None)

rec("p1-25", "kis", "L23_V017", [1108], [(40, 60), (60, 180)], "medium",
    "Strong match: query = drone-from-above bike race; blue-white athlete overtakes 3 others before an uphill then leads to finish. Anchor 44.32s = top-down moment with 4 riders, blue/white leader pulling away from 3. Overtake event ~[40,60]; leading segment continues to ~180 before solo descent/finish arch.",
    "Secondary range [60,180] is the 'leads the rest' phase; Minh may accept only the overtake window.",
    note=None)
