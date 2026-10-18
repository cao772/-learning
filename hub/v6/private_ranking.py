"""Owner-only offline projection. Never imported by public scoring/report runner."""
def rank(public_rows, preferences):
    result=[]
    for row in public_rows:
        boost=preferences.get(row['category'],0)
        if isinstance(boost,bool) or not isinstance(boost,(int,float)) or not -5<=boost<=5:
            raise ValueError('Private category preference must be between -5 and 5')
        result.append({'event_id':row['event_id'],'private_score':row['score']+boost,
                       'public_score':row['score'],'private_boost':boost})
    return sorted(result,key=lambda x:(-x['private_score'],x['event_id']))
