"""Diagnostic, not a replacement for the maintained40-second regression gate."""
import json,os,subprocess,sys,time
from pathlib import Path
probe,evidence=map(Path,sys.argv[1:]);evidence.mkdir();source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();assert source=='85068cedb4babe5302a51d1f035f473f8777cd84'
negative=evidence/'negative-LibraryScene.qml';negative.write_bytes(subprocess.check_output(['git','show','d6e6d69fb296c4c24314f21ad2821865e99a78e2:yt_downloader/qt_quick/LibraryScene.qml']))
results=[];failed=False
for count,scroll,old in [(72,1900,False),(2000,1900,False),(2000,90000,False),(72,1900,True)]:
 label=f'{count}-{scroll}-'+('negative' if old else 'positive');out=evidence/label;out.mkdir();env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QT_QUICK_CONTROLS_STYLE='Basic',VODFORGE_DISABLE_TELEMETRY='1',HOME=str(out),LOCALAPPDATA=str(out),XDG_DATA_HOME=str(out/'.local/share'),PYTHONPATH=str(Path.cwd()))
 if old:env['REFLOW_NEGATIVE_QML']=str(negative)
 start=time.monotonic();row={'label':label,'source':source,'diagnostic_timeout_seconds':180,'maintained_guard_seconds':40}
 try:
  result=subprocess.run([sys.executable,str(probe),'--probe',str(out),str(count),str(scroll)],env=env,capture_output=True,text=True,timeout=180)
  (out/'stdout.log').write_text(result.stdout);(out/'stderr.log').write_text(result.stderr);row['exit']=result.returncode;row['elapsed_seconds']=time.monotonic()-start;assert result.returncode==0
  proof=json.loads((out/'proof.json').read_text());row['blank_samples']=len(proof['blank_faces']);row['max_delegates']=proof['max_delegates'];row['resize_p50_ms']=proof['resize_process_p50_ms']
  if old:assert proof['blank_faces'],'Negative control did not detect blanking'
  else:
   assert not proof['blank_faces'];assert proof['max_delegates']<=proof['max_cap']<count;assert proof['selection_retained'];assert proof['scroll_return_error']<1;assert proof['scroll_cycle_error']<1;assert proof['survivor_replacements']==0;assert proof['hidden_scene_scroll_error']<1
  row['status']='diagnostic assertions passed'
 except BaseException as error:
  failed=True;row['status']='failed';row['error']=str(error);row['elapsed_seconds']=time.monotonic()-start
  if isinstance(error,subprocess.TimeoutExpired):
   (out/'stdout.log').write_bytes(error.stdout or b'');(out/'stderr.log').write_bytes(error.stderr or b'')
 results.append(row);print(json.dumps(row),flush=True);(evidence/'summary.json').write_text(json.dumps({'source':source,'kind':'phase/cost diagnosis only; maintained gate not relabeled','cases':results},indent=2))
raise SystemExit(1 if failed else 0)
