"""Single-user local baseball analysis API."""
import csv,io,json,os,re,shutil,subprocess,threading,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from fastapi import FastAPI,UploadFile,File,HTTPException
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,model_validator
from analysis import inspect_video,pitch_metrics,angle,annotated_export
from sample import generate
ROOT=Path(__file__).parent;DATA=Path(os.environ.get('BASEBALL_DATA',ROOT/'data'));DATA.mkdir(exist_ok=True,parents=True)
app=FastAPI(title='Baseball Analysis');executor=ThreadPoolExecutor(max_workers=1);slots=threading.BoundedSemaphore(3);lock=threading.RLock();jobs={}

def folder(id):
    if not re.fullmatch('[a-f0-9]{32}',id) or not (DATA/id).is_dir():raise HTTPException(404,'Recording not found')
    return DATA/id

def read(id):
    p=folder(id)/'result.json'
    if not p.exists():raise HTTPException(409,'Analysis not ready')
    with lock:return json.loads(p.read_text())

def save(id,result):
    with lock:
        p=folder(id);(p/'result.tmp').write_text(json.dumps(result,allow_nan=False));(p/'result.tmp').replace(p/'result.json')

class Point(BaseModel):
    time:float=Field(ge=0,le=60);point:list[float]
class Pitch(BaseModel):
    id:str=Field(max_length=40);name:str=Field(max_length=80);points:list[Point]=Field(max_length=500)
class Pose(BaseModel):
    time:float=Field(ge=0,le=60);name:str=Field(max_length=60);points:list[list[float]]=Field(min_length=3,max_length=3)
class Calibration(BaseModel):
    points:list[list[float]]=Field(min_length=2,max_length=2);metres:float=Field(gt=0,le=200)
class Review(BaseModel):
    pitches:list[Pitch]=Field(max_length=100);poses:list[Pose]=Field(max_length=200);zone:list[float]|None=None;calibration:Calibration|None=None;note:str=Field(default='',max_length=3000);show_candidates:bool=True
    @model_validator(mode='after')
    def valid(self):
        import math
        coordinates=[p.point for pitch in self.pitches for p in pitch.points]+[p for pose in self.poses for p in pose.points]+(self.calibration.points if self.calibration else [])
        for p in coordinates:
            if len(p)!=2 or any(not math.isfinite(v) or not 0<=v<=1 for v in p):raise ValueError('Coordinates must be finite image-width normalized points')
        if self.zone is not None:
            if len(self.zone)!=4 or any(not math.isfinite(v) or not 0<=v<=1 for v in self.zone) or self.zone[0]>=self.zone[2] or self.zone[1]>=self.zone[3]:raise ValueError('Invalid zone rectangle')
        if len({p.id for p in self.pitches})!=len(self.pitches):raise ValueError('Pitch IDs must be unique')
        for p in self.pitches:pitch_metrics(p.model_dump(),self.calibration.model_dump() if self.calibration else None,self.zone)
        return self

def public(result):
    review=result['review'];result['metrics']=[pitch_metrics(p,review['calibration'],review['zone']) for p in review['pitches']]
    result['angles']=[dict(p,angle=angle(*p['points'])) for p in review['poses']];return result

def queue(id,synthetic=False):
    jobs[id]={'id':id,'status':'queued','progress':0}
    def run():
        try:
            jobs[id]['status']='processing';p=folder(id)
            if synthetic:generate(p/'source.mp4')
            result=inspect_video(p/'source.mp4',lambda v:jobs[id].update(progress=round(v*90)))
            subprocess.run(['ffmpeg','-y','-v','error','-i',str(p/'source.mp4'),'-an','-vf',f"scale={result['width']}:{result['height']}",'-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart',str(p/'playback.mp4')],check=True,capture_output=True,timeout=180)
            result.update(id=id,synthetic=synthetic,review={'pitches':[],'poses':[],'zone':None,'calibration':None,'note':'','show_candidates':True});save(id,result);jobs[id].update(status='ready',progress=100)
        except Exception as e:jobs[id].update(status='error',error=str(e)[:300]);(folder(id)/'error.txt').write_text(str(e)[:300])
        finally:slots.release()
    executor.submit(run);return jobs[id].copy()

@app.post('/api/upload',status_code=202)
async def upload(file:UploadFile=File(...)):
    if Path(file.filename or '').suffix.lower() not in {'.mp4','.mov','.avi','.mkv','.webm'}:raise HTTPException(415,'Upload a video file')
    if not slots.acquire(False):raise HTTPException(429,'Queue full')
    id=uuid.uuid4().hex;p=DATA/id;p.mkdir()
    try:
        size=0
        with (p/'source.mp4').open('wb') as f:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>100*1024*1024:raise HTTPException(413,'Limit is 100 MB')
                f.write(chunk)
        if not size:raise HTTPException(400,'Empty upload')
        return queue(id)
    except Exception:shutil.rmtree(p,ignore_errors=True);slots.release();raise
    finally:await file.close()

@app.post('/api/sample',status_code=202)
def sample():
    if not slots.acquire(False):raise HTTPException(429,'Queue full')
    id=uuid.uuid4().hex;(DATA/id).mkdir();return queue(id,True)
@app.get('/api/recordings')
def recordings():
    return [{'id':p.name,'duration':json.loads((p/'result.json').read_text())['duration'],'synthetic':json.loads((p/'result.json').read_text())['synthetic']} for p in sorted(DATA.iterdir()) if re.fullmatch('[a-f0-9]{32}',p.name) and (p/'result.json').exists()]
@app.get('/api/jobs/{id}')
def status(id:str):
    p=folder(id)
    if id in jobs:return jobs[id].copy()
    return {'id':id,'status':'ready' if (p/'result.json').exists() else 'error','progress':100,'error':(p/'error.txt').read_text() if (p/'error.txt').exists() else 'Processing interrupted'}
@app.get('/api/jobs/{id}/result')
def result(id:str):return public(read(id))
@app.get('/api/jobs/{id}/video')
def video(id:str):return FileResponse(folder(id)/'playback.mp4',media_type='video/mp4')
@app.put('/api/jobs/{id}/review')
def review(id:str,review:Review):
    with lock:
        r=read(id)
        for p in review.pitches:
            if any(s.time>=r['duration'] or s.point[1]>r['aspect'] for s in p.points):raise HTTPException(422,'Pitch point outside recording')
        if any(p.time>=r['duration'] or any(q[1]>r['aspect'] for q in p.points) for p in review.poses):raise HTTPException(422,'Joint point outside recording')
        if review.zone and review.zone[3]>r['aspect']:raise HTTPException(422,'Zone outside image')
        if review.calibration and any(p[1]>r['aspect'] for p in review.calibration.points):raise HTTPException(422,'Calibration outside image')
        r['review']=review.model_dump();save(id,r);return public(r)
@app.get('/api/jobs/{id}/export')
def export(id:str,format:Literal['json','csv']='json'):
    r=public(read(id))
    if format=='json':return Response(json.dumps(r),media_type='application/json',headers={'Content-Disposition':'attachment; filename=baseball-review.json'})
    out=io.StringIO();writer=csv.writer(out);writer.writerow(['pitch','time_seconds','x_image_width','y_image_width','mean_speed','speed_unit'])
    for pitch,m in zip(r['review']['pitches'],r['metrics']):
        name=pitch['name'];name="'"+name if name.lstrip().startswith(('=','+','-','@','\t','\r')) else name
        for p in pitch['points']:writer.writerow([name,p['time'],*p['point'],m['mean_speed'],m['speed_unit']])
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=pitches.csv'})
@app.post('/api/jobs/{id}/render')
def render(id:str):
    r=read(id);p=folder(id)
    if not slots.acquire(False):raise HTTPException(429,'Queue full')
    def work():
        try:
            jobs[id]['render']='processing';annotated_export(p/'source.mp4',p/'annotated.tmp.mp4',r);(p/'annotated.tmp.mp4').replace(p/'annotated.mp4');jobs[id]['render']='ready'
        except Exception as e:jobs[id]['render']='error';jobs[id]['render_error']=str(e)[:300]
        finally:slots.release()
    jobs.setdefault(id,{'id':id,'status':'ready','progress':100})
    if jobs[id].get('render')=='processing':slots.release();raise HTTPException(409,'Already rendering')
    jobs[id]['render']='processing';executor.submit(work);return {'render':'processing'}
@app.get('/api/jobs/{id}/annotated')
def annotated(id:str):
    p=folder(id)/'annotated.mp4'
    if not p.exists():raise HTTPException(409,'Render the annotated clip first')
    return FileResponse(p,media_type='video/mp4',filename='baseball-annotated.mp4')
@app.get('/api/health')
def health():return {'status':'ok'}
app.mount('/',StaticFiles(directory=ROOT/'static',html=True))
