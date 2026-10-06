import time
import pytest
from fastapi.testclient import TestClient
import app as module
from sample import generate

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'DATA',tmp_path);module.jobs.clear()
    with TestClient(module.app) as c:yield c

def wait(c,id):
    for _ in range(200):
        s=c.get('/api/jobs/'+id).json()
        if s['status'] in ['ready','error']:return s
        time.sleep(.05)
    raise AssertionError('Processing timeout')

def test_input_validation(client):
    assert client.post('/api/upload',files={'file':('a.txt',b'a')}).status_code==415
    assert client.post('/api/upload',files={'file':('a.mp4',b'')}).status_code==400
    assert client.get('/api/jobs/unknown/result').status_code==404

def test_review_export_and_persistence(client,tmp_path):
    p=tmp_path/'input.mp4';generate(p)
    id=client.post('/api/upload',files={'file':('sample.mp4',p.read_bytes())}).json()['id'];assert wait(client,id)['status']=='ready'
    r=client.get(f'/api/jobs/{id}/result').json();review=r['review']
    review['pitches']=[{'id':'1','name':'=unsafe','points':[{'time':1,'point':[.2,.2]},{'time':2,'point':[.3,.2]}]}]
    review['poses']=[{'name':'elbow','time':1,'points':[[.1,.1],[.2,.1],[.2,.2]]}]
    review['calibration']={'points':[[0,0],[.1,0]],'metres':1};review['zone']=[.25,.15,.35,.3];review['note']='<script>text only</script>'
    result=client.put(f'/api/jobs/{id}/review',json=review);assert result.status_code==200
    assert result.json()['angles'][0]['angle']==90
    assert result.json()['metrics'][0]['mean_speed']==pytest.approx(3.6)
    assert "'=unsafe" in client.get(f'/api/jobs/{id}/export?format=csv').text
    module.jobs.clear();assert client.get(f'/api/jobs/{id}').json()['status']=='ready'
    assert client.get(f'/api/jobs/{id}/result').json()['review']['note']==review['note']
    assert len(client.get('/api/recordings').json())==1
    assert client.get(f'/api/jobs/{id}/video',headers={'Range':'bytes=0-99'}).status_code==206
    review['pitches'][0]['points'][1]['time']=99;assert client.put(f'/api/jobs/{id}/review',json=review).status_code==422

def test_failed_job_persists(client):
    id=client.post('/api/upload',files={'file':('bad.mp4',b'bad')}).json()['id'];assert wait(client,id)['status']=='error';module.jobs.clear();assert client.get(f'/api/jobs/{id}').json()['status']=='error'

def test_review_geometry_validation():
    with pytest.raises(ValueError):module.Review(pitches=[],poses=[],calibration={'points':[[0,0],[0,0]],'metres':1})
    with pytest.raises(ValueError):module.Review(pitches=[],poses=[],zone=[.4,.2,.1,.3])
