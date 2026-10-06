"""Image-plane baseball review. Candidate extraction is not semantic recognition."""
import math
import cv2
import numpy as np


def angle(a,b,c):
    u=np.array(a,dtype=float)-b;v=np.array(c,dtype=float)-b
    if np.linalg.norm(u)*np.linalg.norm(v)<1e-8:return None
    return round(math.degrees(math.acos(float(np.clip(np.dot(u,v)/np.linalg.norm(u)/np.linalg.norm(v),-1,1)))),2)


def pitch_metrics(pitch,calibration,zone):
    points=sorted(pitch['points'],key=lambda p:p['time']);speeds=[];distance=0
    scale=None
    if calibration:
        a,b=calibration['points'];px=math.dist(a,b)
        if px<.005:raise ValueError('Calibration points are too close')
        scale=calibration['metres']/px
    for a,b in zip(points,points[1:]):
        dt=b['time']-a['time'];delta=math.dist(a['point'],b['point'])
        if dt<=0:raise ValueError('Pitch points must use distinct frame times')
        distance+=delta
        speeds.append({'time':b['time'],'value':delta/dt*(scale*3.6 if scale else 1)})
    endpoint=points[-1]['point'] if points else None
    inside=None if not zone or endpoint is None else zone[0]<=endpoint[0]<=zone[2] and zone[1]<=endpoint[1]<=zone[3]
    return {'id':pitch['id'],'name':pitch['name'],'samples':len(points),'duration':round(points[-1]['time']-points[0]['time'],4) if len(points)>1 else 0,'distance':distance*(scale or 1),'speed_unit':'km/h (image-plane estimate)' if scale else 'normalized-image-width/s','mean_speed':sum(s['value'] for s in speeds)/len(speeds) if speeds else None,'speeds':speeds,'endpoint_inside_zone':inside}


def inspect_video(path,progress=lambda v:None):
    cap=cv2.VideoCapture(str(path));samples=[];previous=None;last=None
    try:
        fps=cap.get(cv2.CAP_PROP_FPS);count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not cap.isOpened() or not math.isfinite(fps) or not 1<=fps<=120 or not 0<count<=7200:raise ValueError('Use a decodable 1–120 fps video, at most 60 seconds')
        if count/fps>60:raise ValueError('Clip limit is 60 seconds')
        sw=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));sh=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if sw*sh>16000000:raise ValueError('Frame resolution exceeds 16 MP')
        n=0;w=h=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            if n>=7200 or n/fps>=60:raise ValueError('Decoded clip exceeds processing limit')
            h0,w0=frame.shape[:2];w= min(w0,960);h=round(h0*w/w0);frame=cv2.resize(frame,(w,h));gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            candidate=None
            if previous is not None:
                diff=cv2.absdiff(gray,previous);mask=cv2.inRange(frame,(185,185,185),(255,255,255));mask[diff<18]=0
                contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);options=[]
                for c in contours:
                    area=cv2.contourArea(c);(x,y),r=cv2.minEnclosingCircle(c)
                    if 4<=area<=600 and 1.5<=r<=18:
                        circularity=4*math.pi*area/max(cv2.arcLength(c,True)**2,1)
                        if circularity>=.45:options.append((circularity,x/w,y/w,r/w))
                if options:
                    selected=max(options,key=lambda p:p[0]-(math.dist([p[1],p[2]],last) if last else 0)*2)
                    candidate={'point':[selected[1],selected[2]],'radius':selected[3],'method':'bright moving candidate','confidence':None};last=candidate['point']
                else:last=None
            samples.append({'time':round(n/fps,6),'ball':candidate});previous=gray;n+=1
            if n%20==0:progress(min(.9,n/count))
        if not n:raise ValueError('No frames decoded')
        return {'fps':fps,'duration':n/fps,'width':w,'height':h,'aspect':h/w,'source_width':sw,'source_height':sh,'frames':samples,'candidate_count':sum(s['ball'] is not None for s in samples)}
    finally:cap.release()


def annotated_export(source,destination,record):
    import subprocess
    cap=cv2.VideoCapture(str(source));w=record['width'];h=record['height'];fps=record['fps'];n=0
    proc=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size',f'{w}x{h}','-framerate',str(fps),'-i','-','-an','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart',str(destination)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    def px(point):return tuple(round(v*w) for v in point)
    try:
        while True:
            ok,frame=cap.read()
            if not ok:break
            frame=cv2.resize(frame,(w,h));time=n/fps;color=(235,222,64)
            z=record['review'].get('zone')
            if z:cv2.rectangle(frame,px(z[:2]),px(z[2:]),color,1)
            for pitch in record['review']['pitches']:
                pts=[p for p in pitch['points'] if p['time']<=time]
                for a,b in zip(pts,pts[1:]):cv2.line(frame,px(a['point']),px(b['point']),color,2)
                for p in pts:cv2.circle(frame,px(p['point']),4,color,1)
            observation=record['frames'][min(n,len(record['frames'])-1)]['ball']
            if observation and record['review']['show_candidates']:cv2.circle(frame,px(observation['point']),max(4,round(observation['radius']*w)),(70,175,255),1)
            for pose in record['review']['poses']:
                if abs(pose['time']-time)<=.5:
                    for p in pose['points']:cv2.circle(frame,px(p),5,color,-1)
                    for a,b in zip(pose['points'],pose['points'][1:]):cv2.line(frame,px(a),px(b),color,2)
            cv2.putText(frame,'BASEBALL REVIEW | image-plane annotations',(15,25),cv2.FONT_HERSHEY_SIMPLEX,.5,color,1)
            if record['synthetic']:cv2.putText(frame,'GENERATED TEST FOOTAGE',(15,h-18),cv2.FONT_HERSHEY_SIMPLEX,.5,(180,180,180),1)
            proc.stdin.write(frame.tobytes());n+=1
        proc.stdin.close();error=proc.stderr.read();code=proc.wait(timeout=90)
        if code:raise ValueError(error.decode()[:300])
    finally:
        cap.release()
        if proc.poll() is None:proc.kill();proc.wait()
