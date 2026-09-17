# Exploratory results

R counts are out of113; full precision and paired evidence in arms.json.

| Arm | R1 | R5 | R10 | R20 | MRR20 | Complete targets in100 | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| PR91 control |49|77|82|87|0.529989016565|78|selected|
|packet-e|49|77|81|83|0.533912228381|71|NEGATIVE|
|segment-v2|49|77|82|87|0.529989016565|78|INCONCLUSIVE|
|semantic|10|21|25|29|0.128599522405|12|NEGATIVE|
|semantic-integrated|47|62|77|84|0.483334478871|73|NEGATIVE|
|yolo|50|76|82|87|0.537068662583|78|INCONCLUSIVE|
|query-variants|48|63|75|83|0.489140467764|73|NEGATIVE|
|semantic-dense|26|42|49|61|0.297818384837|23|NEGATIVE|
|semantic-dense-integrated|41|65|80|88|0.472808896956|74|NEGATIVE|
|query-translation/provider|17|25|28|33|0.181450825477|19|NEGATIVE|
|query-translation|45|61|72|80|0.469376181687|73|NEGATIVE|
|semantic-grounding/provider|26|42|49|61|0.297818384837|42|NEGATIVE|
|semantic-grounding|44|64|74|89|0.468521607764|75|NEGATIVE|
