"""Novel-video semantic admission replaces only redundant-video tail frames."""
from collections import Counter
def admit(base,semantic):
    result=list(base);counts=Counter(f['video_id'] for f in result)
    added=0
    for f in semantic:
        if f['video_id'] in counts:continue
        removable=next((i for i in range(len(result)-1,0,-1) if counts[result[i]['video_id']]>1),None)
        if removable is None:break
        old=result.pop(removable);counts[old['video_id']]-=1
        result.append(f);counts[f['video_id']]=1;added+=1
        if added==20:break
    return [{**f,'rank':i+1} for i,f in enumerate(result)]
