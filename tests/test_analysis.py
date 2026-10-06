import math
import cv2
import numpy as np
import pytest
from analysis import angle,pitch_metrics,inspect_video,annotated_export
from sample import generate

def test_angles():
    assert angle([0,0],[1,0],[1,1])==90
    assert angle([0,0],[1,0],[2,0])==180
    assert angle([1,0],[1,0],[2,0]) is None

def test_calibrated_speed_and_zone():
    p={'id':'1','name':'Pitch','points':[{'time':0,'point':[.1,.2]},{'time':.5,'point':[.3,.2]}]}
    r=pitch_metrics(p,{'points':[[0,0],[.2,0]],'metres':2},[.2,.1,.4,.3])
    assert r['mean_speed']==pytest.approx(14.4)
    assert r['endpoint_inside_zone'] is True
    assert pitch_metrics(p,None,None)['mean_speed']==pytest.approx(.4)

def test_reject_duplicate_timestamps():
    with pytest.raises(ValueError):pitch_metrics({'id':'a','name':'a','points':[{'time':0,'point':[0,0]},{'time':0,'point':[1,0]}]},None,None)

def test_empty_metrics():
    r=pitch_metrics({'id':'a','name':'a','points':[]},None,None)
    assert r['mean_speed'] is None and r['endpoint_inside_zone'] is None

@pytest.fixture(scope='module')
def fixture_video(tmp_path_factory):
    p=tmp_path_factory.mktemp('footage')/'sample.mp4';generate(p);return p

def test_candidate_extraction(fixture_video):
    r=inspect_video(fixture_video)
    assert r['duration']==8 and r['fps']==30 and len(r['frames'])==240
    assert r['candidate_count']>100
    assert all(f['ball']['confidence'] is None for f in r['frames'] if f['ball'])

def test_empty_scene(tmp_path):
    p=tmp_path/'empty.mp4';v=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*'mp4v'),20,(320,180))
    for _ in range(30):v.write(np.zeros((180,320,3),np.uint8))
    v.release();assert inspect_video(p)['candidate_count']==0

def test_corrupt(tmp_path):
    p=tmp_path/'bad.mp4';p.write_bytes(b'no video')
    with pytest.raises(ValueError):inspect_video(p)

def test_render_source_frame_count(fixture_video,tmp_path):
    r=inspect_video(fixture_video);r['synthetic']=True;r['review']={'pitches':[{'points':[{'time':.5,'point':[.2,.2]},{'time':1,'point':[.7,.3]}]}],'poses':[{'time':1,'points':[[.1,.1],[.2,.1],[.2,.2]]}],'zone':[.65,.15,.85,.4],'show_candidates':True}
    out=tmp_path/'annotated.mp4';annotated_export(fixture_video,out,r)
    cap=cv2.VideoCapture(str(out));assert cap.get(cv2.CAP_PROP_FRAME_COUNT)==240;assert cap.get(cv2.CAP_PROP_FPS)==30;cap.release()
