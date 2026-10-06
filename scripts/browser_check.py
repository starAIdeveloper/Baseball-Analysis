"""End-to-end local validation, optional self-started server."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];ART=ROOT/'artifacts';ART.mkdir(exist_ok=True)
url=os.environ.get('BASEBALL_URL','http://127.0.0.1:8012');server=None;temp=tempfile.TemporaryDirectory()
try:
    if os.environ.get('BASEBALL_START_SERVER'):
        env=dict(os.environ,BASEBALL_DATA=temp.name)
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',url.rsplit(':',1)[1]],cwd=ROOT,env=env,stdout=(ART/'server.log').open('w'),stderr=subprocess.STDOUT)
        for _ in range(100):
            try:urllib.request.urlopen(url+'/api/health',timeout=1);break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('Server did not start')
    checks=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('BASEBALL_CHROMIUM') or None,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1536,'height':1100},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url);page.locator('#sample').click();page.wait_for_function("document.querySelector('#saveStatus').textContent==='Review loaded'",timeout=90000)
        assert page.locator('#sourceLabel').inner_text()=='GENERATED TEST FOOTAGE';assert int(page.locator('#candidates').inner_text())>100;checks.append('generated video processed with actual candidates')
        page.locator('#newPitch').click();page.locator('#import').click();assert 'Unsaved' in page.locator('#saveStatus').inner_text();checks.append('candidate import into editable pitch')
        page.locator('#seek').evaluate('(e)=>{e.value=1;e.dispatchEvent(new Event("input"))}');page.wait_for_timeout(200)
        def mark(tool,points):
            page.locator(f'[data-tool="{tool}"]').click();box=page.locator('#overlay').bounding_box()
            for x,y in points:page.mouse.click(box['x']+x*box['width'],box['y']+y*box['width'])
        mark('zone',[(.65,.25),(.9,.7)]);mark('joint',[(.25,.3),(.4,.3),(.4,.55)]);assert '90.0°' in page.locator('#angles').inner_text();checks.append('manual joint angle and image zone')
        mark('calibration',[(.1,.8),(.3,.8)]);assert 'Distance calibrated'==page.locator('#calibStatus').inner_text();checks.append('projected speed calibration')
        page.locator('#note').fill('<script>alert(1)</script> Reviewed sample');page.locator('#save').click();page.wait_for_function("document.querySelector('#saveStatus').textContent==='Saved to local recording'");checks.append('persistent annotations')
        with page.expect_download() as d:page.locator('#csv').click()
        assert d.value.suggested_filename=='pitches.csv';checks.append('CSV download')
        page.locator('#render').click();page.wait_for_function("!document.querySelector('#download').disabled",timeout=90000)
        with page.expect_download() as d:page.locator('#download').click()
        d.value.save_as(ART/'annotated.mp4');checks.append('actual annotated MP4 render and download')
        identity=page.locator('#recordings').input_value();page.reload();page.locator('#recordings').select_option(identity);page.wait_for_function("document.querySelector('#saveStatus').textContent==='Review loaded'");assert 'Reviewed sample' in page.locator('#note').input_value();checks.append('reload persistence')
        page.locator('#seek').evaluate('(e)=>{e.value=2;e.dispatchEvent(new Event("input"))}');page.wait_for_timeout(300);page.screenshot(path=str(ART/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200);assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');page.screenshot(path=str(ART/'mobile.png'),full_page=True);checks.append('390px mobile layout without overflow')
        from sample import generate
        upload=Path(temp.name)/'upload-test.mp4';generate(upload);page.locator('#upload').set_input_files(upload);page.wait_for_function("document.querySelector('#sourceLabel').textContent==='UPLOADED SOURCE'",timeout=90000);checks.append('real file upload path')
        assert not errors,errors;browser.close()
    report={'status':'passed','checks':checks,'console_errors':errors,'viewports':['1536x1100','390x844']};(ART/'browser-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if server:server.terminate();server.wait(timeout=10)
    temp.cleanup()
