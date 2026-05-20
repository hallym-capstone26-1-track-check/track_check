import urllib.request, json
data = json.dumps({
    'dept_name': '소프트웨어학부', 
    'courses': [
        {'course_name': '빅데이터개론', 'credits': 3, 'grade': 'A+'}, 
        {'course_name': '데이터사이언스기초', 'credits': 3, 'grade': 'A+'}, 
        {'course_name': '인공지능기초', 'credits': 3, 'grade': 'A+'}, 
        {'course_name': '머신러닝', 'credits': 3, 'grade': 'A+'}
    ]
}).encode('utf-8')
req = urllib.request.Request('http://localhost:8000/api/v1/analyze', data=data, headers={'Content-Type':'application/json'})
try:
    res = urllib.request.urlopen(req)
    d = json.loads(res.read().decode())
    track = [t for t in d['track_results'] if t['track_id'] == '소프트웨어학부__빅데이터AI융합트랙'][0]
    print('is_completed:', track['is_completed'])
    print('taken_courses:', track['taken_courses'])
    print('missing_courses:', track['missing_courses'])
    for r in track['rule_results']:
        print(f" - {r['rule_type']} satisfied={r['satisfied']} taken={r.get('taken_courses')}")
except Exception as e:
    print('Error:', e)
