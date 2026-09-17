"""Fixed 80/20 candidate allocation, no truth or scoring changes."""
def admit(base,semantic):
    result=list(base[:80]);seen={f['frame_id'] for f in result}
    for f in semantic+base[80:]:
        if f['frame_id'] in seen:continue
        result.append(f);seen.add(f['frame_id'])
        if len(result)>=100:break
    return [{**f,'rank':i+1} for i,f in enumerate(result)]
