"""Read-only offscreen fixture trace; no handler-property writes or native GUI."""
import importlib.util,json,os,platform,sys,tempfile,time
from pathlib import Path
source=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(source));os.chdir(source)
from PySide6.QtCore import QObject,QEvent,QTimer,QPointF
from PySide6.QtGui import QGuiApplication
from PySide6 import __version__ as qt_binding
import pytest
spec=importlib.util.spec_from_file_location('ax_fixture',source/'engineering-quality/tests/test_qt_stone_button_accessibility.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=module.hover_embedded_video;started=time.monotonic();events=[];samples=[]
app=QGuiApplication.instance() or QGuiApplication([])
def capture(window):
 surface=window.findChild(QObject,'watchVideoSurface');overlay=window.findChild(QObject,'embeddedPlayerOverlay')
 point=surface.mapToScene(QPointF(surface.width()/2,surface.height()/2));ancestors=[];item=surface
 while item:
  ancestors.append({'name':item.objectName(),'visible':item.isVisible(),'size':[item.width(),item.height()],'clip':item.clip()})
  item=item.parentItem()
 popups=[{'name':obj.objectName(),'visible':obj.property('visible'),'opened':obj.property('opened')} for obj in window.findChildren(QObject) if obj.metaObject().indexOfProperty('opened')>=0]
 return {'elapsed_ms':(time.monotonic()-started)*1000,'point':[point.x(),point.y()],'surface_hovered':overlay.property('surfaceHovered'),'controls_shown':overlay.property('controlsShown'),'presentation_available':overlay.property('presentationAvailable'),'window_visible':window.isVisible(),'window_exposed':window.isExposed(),'window_active':window.isActive(),'window_size':[window.width(),window.height()],'ancestors':ancestors,'popups':popups,'hover_handlers':[{'class':obj.metaObject().className(),'hovered':obj.property('hovered'),'enabled':obj.property('enabled'),'accepted_devices':str(obj.property('acceptedDevices'))} for obj in surface.parentItem().findChildren(QObject) if 'HoverHandler' in obj.metaObject().className()]}
class Events(QObject):
 def eventFilter(self,obj,event):
  if obj is self.window and event.type() in (QEvent.MouseMove,QEvent.Enter,QEvent.Leave,QEvent.HoverMove,QEvent.Resize,QEvent.Show,QEvent.Hide,QEvent.WindowActivate,QEvent.WindowDeactivate):
   row={'elapsed_ms':(time.monotonic()-started)*1000,'type':event.type().name}
   if hasattr(event,'position'):row['position']=[event.position().x(),event.position().y()]
   events.append(row)
  return False
recorder=Events()
def traced(window):
 recorder.window=window;window.installEventFilter(recorder);timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:samples.append(capture(window)));timer.start();samples.append(capture(window))
 try:original(window)
 finally:samples.append(capture(window));timer.stop();window.removeEventFilter(recorder)
module.hover_embedded_video=traced
passed=False;error=None
with tempfile.TemporaryDirectory(prefix='vf-hover-case-') as tmp:
 patch=pytest.MonkeyPatch()
 try:module.test_stone_buttons_expose_named_press_actions_and_hide_other_views(Path(tmp),patch);passed=True
 except Exception as exc:error=repr(exc)
 finally:patch.undo()
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps({'passed':passed,'error':error,'platform':platform.platform(),'machine':platform.machine(),'qt_binding':qt_binding,'qpa':app.platformName(),'events':events,'samples':samples,'scope':'Offscreen normal fixture routing only; no native product qualification'},indent=2)+'\n')
print(json.dumps({'passed':passed,'events':len(events),'samples':len(samples),'output':str(output)}));sys.exit(0 if passed else 1)
