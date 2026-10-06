"""Original generated test footage, not an athlete measurement benchmark."""
import cv2
import numpy as np

def generate(path):
    w,h,fps=960,540,30
    out=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
    if not out.isOpened():raise ValueError('Cannot create sample')
    try:
        for n in range(240):
            frame=np.full((h,w,3),(30,24,17),np.uint8)
            cv2.rectangle(frame,(0,330),(960,540),(50,85,43),-1)
            cv2.ellipse(frame,(450,500),(480,130),0,180,360,(72,101,140),-1)
            for x in range(30,960,60):cv2.rectangle(frame,(x,40),(x+20,48),(100,100,95),-1)
            # Procedural pitcher and batter silhouettes.
            for x,y in [(150,280),(825,300)]:
                cv2.circle(frame,(x,y-75),18,(145,112,83),-1);cv2.line(frame,(x,y-50),(x,y+55),(115,80,40),20)
                cv2.line(frame,(x,y+55),(x-35,y+145),(185,170,150),12);cv2.line(frame,(x,y+55),(x+28,y+145),(185,170,150),12)
                cv2.line(frame,(x,y-35),(x+65,y-5),(115,80,40),12)
            cv2.line(frame,(840,270),(875,155),(90,145,190),8)
            phase=(n%80)/80
            if .1<=phase<=.8:
                t=(phase-.1)/.7;x=round(210+560*t);y=round(255-75*np.sin(np.pi*t)+20*t)
                cv2.circle(frame,(x,y),6,(248,248,248),-1)
            cv2.putText(frame,'GENERATED PITCH TRACKING TEST',(22,28),cv2.FONT_HERSHEY_SIMPLEX,.55,(160,180,180),1)
            out.write(frame)
    finally:out.release()
