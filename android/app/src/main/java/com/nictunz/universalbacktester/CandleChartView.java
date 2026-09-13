package com.nictunz.universalbacktester;

import android.content.Context;
import android.graphics.*;
import android.view.*;
import org.json.*;
import java.util.*;

/** Offline OHLC chart. Only the visible window is kept in memory. */
public class CandleChartView extends View {
    public interface Navigator { void move(int bars); void zoom(float factor); void inspect(long timestamp); void drawing(JSONObject shape); }
    private final Paint p = new Paint(3);
    private final Navigator nav;
    private final ScaleGestureDetector scale;
    private final GestureDetector gestures;
    private List<double[]> candles = Collections.emptyList();
    private JSONArray trades = new JSONArray();
    private final Map<JSONObject,long[]> tradeTimes=new IdentityHashMap<>();
    private final Set<Long> entryTimes=new HashSet<>();
    private final Map<Long,JSONObject> overlays = new HashMap<>();
    private JSONArray drawings = new JSONArray();
    private boolean showEma=true, showBands=false;
    private int pane=1, drawingMode=0;
    private long anchorTime;
    private double anchorPrice;
    private boolean anchorSet;
    public void setOverlays(JSONArray rows){overlays.clear();if(rows!=null)for(int i=0;i<rows.length();i++){JSONObject row=rows.optJSONObject(i);if(row!=null)overlays.put(row.optLong("timestamp"),row);}invalidate();}
    public void options(boolean ema,boolean bands,int selectedPane){showEma=ema;showBands=bands;pane=selectedPane;invalidate();}
    public void setDrawings(JSONArray values){drawings=values==null?new JSONArray():values;invalidate();}
    public void drawingMode(int mode){drawingMode=mode;anchorSet=false;}
    public long selectedTime(){return candles.isEmpty()?0:(long)candles.get(selected<0?candles.size()-1:selected)[0];}
    public double selectedPrice(){return candles.isEmpty()?0:candles.get(selected<0?candles.size()-1:selected)[4];}
    public void focusTime(long timestamp){if(candles.isEmpty())return;int at=index(timestamp);selected=at<0?candles.size()-1:at;nav.inspect((long)candles.get(selected)[0]);invalidate();}
    private void drawTap(float x,float yy){
        if(drawingMode==0||candles.isEmpty()||yy<top||yy>bottom)return;
        long time=selectedTime();double price=max-(yy-top)/(bottom-top)*(max-min);
        if(drawingMode==2&&!anchorSet){anchorTime=time;anchorPrice=price;anchorSet=true;invalidate();return;}
        try{
            JSONObject shape=new JSONObject();shape.put("type",drawingMode==1?"horizontal":"trend");
            shape.put("time",time);shape.put("price",price);
            if(drawingMode==2){shape.put("time2",anchorTime);shape.put("price2",anchorPrice);}
            drawingMode=0;anchorSet=false;nav.drawing(shape);
        }catch(JSONException ignored){}
    }
    private JSONArray audit = new JSONArray();
    private final Map<Long,JSONObject> auditValues=new HashMap<>();
    public void setAudit(JSONArray rows){audit=rows==null?new JSONArray():rows;auditValues.clear();for(int i=0;i<audit.length();i++){JSONObject row=audit.optJSONObject(i);if(row!=null)auditValues.put(row.optLong("timestamp"),row);}invalidate();}
    private int selected = -1;
    private double min, max;
    private float left, right, top, bottom, step;
    private float drag;
    private boolean inspecting;
    private final Set<Long> qualityTimes=new HashSet<>();
    public void setQuality(JSONArray rows){qualityTimes.clear();if(rows!=null)for(int i=0;i<rows.length();i++){JSONObject row=rows.optJSONObject(i);if(row!=null)qualityTimes.add(row.optLong("timestamp"));}invalidate();}
    private boolean validBar(double[] b){return b.length>=6&&Double.isFinite(b[1])&&Double.isFinite(b[2])&&Double.isFinite(b[3])&&Double.isFinite(b[4])&&b[3]>0&&b[3]<=Math.min(b[1],b[4])&&b[2]>=Math.max(b[1],b[4]);}
    private static final int UP = Color.rgb(38,166,154), DOWN = Color.rgb(239,83,80);
    public CandleChartView(Context c, Navigator n) {
        super(c); nav=n; setBackgroundColor(Color.rgb(16,19,24));
        scale=new ScaleGestureDetector(c,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            public boolean onScale(ScaleGestureDetector d){ inspecting=false;nav.zoom(d.getScaleFactor()); return true; }
        });
        gestures=new GestureDetector(c,new GestureDetector.SimpleOnGestureListener(){
            public boolean onDown(MotionEvent e){drag=0;inspecting=false; return true;}
            public boolean onScroll(MotionEvent a,MotionEvent b,float dx,float dy){
                if(scale.isInProgress()||inspecting) return true;
                selected=-1; drag+=dx/Math.max(1,step);
                if(Math.abs(drag)>=2){int count=(int)drag; drag-=count; nav.move(count);} return true;
            }
            public boolean onSingleTapUp(MotionEvent e){ select(e.getX()); drawTap(e.getX(),e.getY()); performClick(); return true; }
            public void onLongPress(MotionEvent e){inspecting=true;select(e.getX());}
        });
    }
    public void setData(List<double[]> data,JSONArray log){
        candles=data;trades=new JSONArray();tradeTimes.clear();entryTimes.clear();qualityTimes.clear();selected=-1;
        if(!data.isEmpty()&&log!=null){
            long first=(long)data.get(0)[0],last=(long)data.get(data.size()-1)[0];
            for(int i=0;i<log.length();i++){JSONObject t=log.optJSONObject(i);if(t==null)continue;
                long en=millis(t.optString("entry_time")),ex=millis(t.optString("exit_time"));
                if(en<0||ex<first||en>last)continue;
                trades.put(t);tradeTimes.put(t,new long[]{en,ex});entryTimes.add(en);
            }
        }
        invalidate();
    }
    private void select(float x){if(candles.isEmpty())return;selected=Math.max(0,Math.min(candles.size()-1,(int)((x-left)/Math.max(1,step))));nav.inspect((long)candles.get(selected)[0]);invalidate();}
    @Override public boolean performClick(){super.performClick();return true;}
    @Override public boolean onTouchEvent(MotionEvent e){
        if(getParent()!=null)getParent().requestDisallowInterceptTouchEvent(e.getActionMasked()!=MotionEvent.ACTION_UP&&e.getActionMasked()!=MotionEvent.ACTION_CANCEL);
        scale.onTouchEvent(e);
        if(inspecting&&e.getActionMasked()==MotionEvent.ACTION_MOVE&&e.getPointerCount()==1)select(e.getX());
        gestures.onTouchEvent(e);
        if(e.getActionMasked()==MotionEvent.ACTION_UP||e.getActionMasked()==MotionEvent.ACTION_CANCEL)inspecting=false;
        return true;
    }
    private float d(float x){return x*getResources().getDisplayMetrics().density;}
    private float y(double price){return bottom-(float)((price-min)/(max-min))*(bottom-top);}
    private String number(double v){return String.format(Locale.US,"%.6f",v).replaceAll("0+$", "").replaceAll("\\.$", "");}
    private void text(Canvas c,String s,float x,float y,int color,float size){p.setColor(color);p.setTextSize(d(size));p.setStyle(Paint.Style.FILL);c.drawText(s,x,y,p);}
    private String time(long ms){java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("MM-dd HH:mm",Locale.US);f.setTimeZone(TimeZone.getTimeZone("UTC"));return f.format(new Date(ms));}
    static long millis(String s){
        try { java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss",Locale.US);f.setTimeZone(TimeZone.getTimeZone("UTC"));return f.parse(s).getTime(); }catch(Exception e){return -1;}
    }
    private int index(long ms){
        int lo=0,hi=candles.size()-1;
        while(lo<=hi){int m=(lo+hi)>>>1;long t=(long)candles.get(m)[0];if(t==ms)return m;if(t<ms)lo=m+1;else hi=m-1;}return -1;
    }
    private void level(Canvas c,double price,int a,int b,int color,String name){
        if(!Double.isFinite(price)||price<=0||price<min||price>max)return;
        p.setColor(color);p.setStrokeWidth(d(1));float yy=y(price);
        c.drawLine(left+step*(a+.5f),yy,left+step*(b+.5f),yy,p);
        text(c,name+" "+number(price),left+step*(a+.5f)+d(3),yy-d(3),color,10);
    }
    @Override protected void onDraw(Canvas c){
        super.onDraw(c);left=d(8);right=getWidth()-d(82);top=d(50);bottom=Math.max(top+d(40),getHeight()-d(pane>0&&getHeight()>d(320)?180:78));
        if(candles.isEmpty()){text(c,"DB를 선택하세요",d(16),d(40),Color.LTGRAY,14);return;}
        step=(right-left)/candles.size();min=Double.POSITIVE_INFINITY;max=Double.NEGATIVE_INFINITY;double vmax=1;
        for(double[] b:candles){if(!validBar(b))continue;min=Math.min(min,b[3]);max=Math.max(max,b[2]);if(Double.isFinite(b[5])&&b[5]>=0)vmax=Math.max(vmax,b[5]);}
        if(!Double.isFinite(min)||!Double.isFinite(max)){text(c,"유효한 가격 데이터가 없습니다 · 데이터 검사 확인",d(8),d(40),Color.YELLOW,12);return;}
        double pad=Math.max((max-min)*.08,Math.abs(max)*.0001);min-=pad;max+=pad;
        p.setStrokeWidth(d(1));
        for(int i=0;i<=5;i++){float yy=top+(bottom-top)*i/5;p.setColor(Color.rgb(40,44,52));c.drawLine(left,yy,right,yy,p);text(c,number(max-(max-min)*i/5),right+d(4),yy,Color.LTGRAY,10);}
        for(int i=0;i<=6;i++){float xx=left+(right-left)*i/6;p.setColor(Color.rgb(32,36,42));c.drawLine(xx,top,xx,bottom+d(48),p);}
        for(int i=0;i<candles.size();i++){
            double[] b=candles.get(i);float x=left+step*(i+.5f);int col=b[4]>=b[1]?UP:DOWN;
            if(qualityTimes.contains((long)b[0])||!validBar(b)){p.setColor(Color.argb(45,255,180,50));c.drawRect(x-step*.5f,top,x+step*.5f,bottom,p);}
            if(!validBar(b))continue;
            p.setColor(col);p.setStrokeWidth(Math.max(1,d(.8f)));c.drawLine(x,y(b[2]),x,y(b[3]),p);
            c.drawRect(x-Math.max(.6f,step*.32f),Math.min(y(b[1]),y(b[4])),x+Math.max(.6f,step*.32f),Math.max(y(b[1]),y(b[4]))+1,p);
            if(Double.isFinite(b[5])&&b[5]>=0){p.setAlpha(90);c.drawRect(x-step*.32f,bottom+d(48)-(float)(b[5]/vmax)*d(40),x+step*.32f,bottom+d(48),p);p.setAlpha(255);}
        }
        c.save();c.clipRect(left,top,right,bottom);
        if(showBands){overlay(c,"bb_upper",Color.rgb(96,125,139));overlay(c,"bb_mid",Color.rgb(96,125,139));overlay(c,"bb_lower",Color.rgb(96,125,139));}
        if(showEma){overlay(c,"ema20",Color.rgb(255,193,7));overlay(c,"ema60",Color.rgb(66,165,245));overlay(c,"ema200",Color.rgb(171,71,188));}
        for(int j=0;j<trades.length();j++){
            JSONObject t=trades.optJSONObject(j);if(t==null)continue;
            long[] times=tradeTimes.get(t);if(times==null)continue;long en=times[0],ex=times[1];
            long first=(long)candles.get(0)[0],last=(long)candles.get(candles.size()-1)[0];
            if(ex<first||en>last)continue;
            int a=index(en),b=index(ex),aa=a<0?0:a,bb=b<0?candles.size()-1:b;
            level(c,t.optDouble("tp_price",Double.NaN),aa,bb,UP,"TP");
            level(c,t.optDouble("sl_price",Double.NaN),aa,bb,DOWN,"SL");
            if(a>=0){boolean isLong=t.optString("side").equals("LONG");float x=left+step*(a+.5f),yy=y(t.optDouble("avg_entry_price",t.optDouble("entry_price")));p.setColor(isLong?UP:DOWN);c.drawCircle(x,yy,d(4),p);text(c,isLong?"▲ LONG":"▼ SHORT",x,yy+(isLong?d(18):-d(10)),isLong?UP:DOWN,10);}
            if(b>=0){float x=left+step*(b+.5f),yy=y(t.optDouble("exit_price"));text(c,"◆ "+t.optString("reason")+" "+String.format(Locale.US,"%+.2f",t.optDouble("pnl")),x,yy-d(8),Color.rgb(191,110,255),10);}
        }
        for(int j=0;j<audit.length();j++){
            JSONObject r=audit.optJSONObject(j);if(r==null)continue;
            int at=index(r.optLong("timestamp"));if(at<0)continue;
            if(r.optBoolean("dual_touch"))text(c,"⚠ DUAL · SL 우선",left+step*(at+.5f),top+d(12),Color.rgb(255,183,77),10);
            boolean recorded=entryTimes.contains(r.optLong("timestamp"));
            if(r.optBoolean("entry")&&!recorded)text(c,"◆ "+r.optString("position")+" 진입",left+step*(at+.5f),y(candles.get(at)[4])-d(10),Color.CYAN,10);
            // The trace also contains still-open positions absent from closed trades.
            double tp=r.optDouble("tp",Double.NaN),sl=r.optDouble("sl",Double.NaN);
            for(double price:new double[]{tp,sl}){
                if(!Double.isFinite(price)||price<min||price>max)continue;
                p.setColor(price==tp?UP:DOWN);p.setStrokeWidth(d(1));
                c.drawLine(left+step*at,y(price),left+step*(at+1),y(price),p);
            }
        }
        drawAnnotations(c);
        c.restore();
        if(pane>0&&getHeight()>d(320))drawPane(c,bottom+d(58),getHeight()-d(24));
        String legend=(showEma?"EMA 20/60/200  ":"")+(showBands?"BB 20·2σ  ":"")+(drawingMode==0?"":drawingMode==1?"수평선: 가격 터치":anchorSet?"추세선: 두 번째 점 터치":"추세선: 첫 번째 점 터치");
        text(c,legend,d(8),top+d(11),Color.LTGRAY,10);
        int k=selected>=0?selected:candles.size()-1;double[] b=candles.get(k);
        text(c,"O "+number(b[1])+"  H "+number(b[2])+"  L "+number(b[3]),d(8),d(18),Color.LTGRAY,11);
        text(c,"C "+number(b[4])+"  V "+number(b[5])+"  "+time((long)b[0])+" UTC",d(8),d(35),b[4]>=b[1]?UP:DOWN,11);
        if(selected>=0){float x=left+step*(selected+.5f);p.setColor(Color.GRAY);p.setPathEffect(new DashPathEffect(new float[]{d(4),d(4)},0));c.drawLine(x,top,x,bottom,p);c.drawLine(left,y(b[4]),right,y(b[4]),p);p.setPathEffect(null);}
        text(c,time((long)candles.get(0)[0]),left,getHeight()-d(12),Color.GRAY,10);
        text(c,time((long)candles.get(candles.size()-1)[0]),Math.max(left,right-d(96)),getHeight()-d(12),Color.GRAY,10);
    }

    private void overlay(Canvas c,String key,int color){
        p.setColor(color);p.setStrokeWidth(d(1));boolean have=false;float px=0,py=0;
        for(int i=0;i<candles.size();i++){
            JSONObject row=overlays.get((long)candles.get(i)[0]);double v=row==null?Double.NaN:row.optDouble(key,Double.NaN);
            if(!Double.isFinite(v)){have=false;continue;}float xx=left+step*(i+.5f),yy=y(v);
            if(have)c.drawLine(px,py,xx,yy,p);px=xx;py=yy;have=true;
        }
    }
    private float timeX(long time){
        if(candles.size()<2)return left+step*.5f;
        int lo=0,hi=candles.size()-1;
        while(lo<hi){int mid=(lo+hi)>>>1;if(candles.get(mid)[0]<time)lo=mid+1;else hi=mid;}
        int a=Math.max(0,lo-1),b=Math.min(candles.size()-1,a+1);
        if(time>candles.get(candles.size()-1)[0]){b=candles.size()-1;a=b-1;}
        double fraction=(time-candles.get(a)[0])/Math.max(1,candles.get(b)[0]-candles.get(a)[0]);
        return left+step*(float)(a+.5+fraction);
    }
    private void drawAnnotations(Canvas c){
        for(int i=0;i<drawings.length();i++){
            JSONObject shape=drawings.optJSONObject(i);if(shape==null)continue;
            double price=shape.optDouble("price",Double.NaN);if(!Double.isFinite(price))continue;
            p.setColor(Color.rgb(255,213,79));p.setStrokeWidth(d(1.5f));
            if(shape.optString("type").equals("horizontal")){
                if(price>=min&&price<=max){c.drawLine(left,y(price),right,y(price),p);text(c,"메모 "+number(price),left+d(4),y(price)-d(3),Color.YELLOW,10);}
            }else if(Double.isFinite(shape.optDouble("price2",Double.NaN))){
                c.drawLine(timeX(shape.optLong("time")),y(price),timeX(shape.optLong("time2")),y(shape.optDouble("price2")),p);
            }
        }
        if(anchorSet){p.setColor(Color.YELLOW);c.drawCircle(timeX(anchorTime),y(anchorPrice),d(4),p);}
    }
    private void drawPane(Canvas c,float upper,float lower){
        if(lower-upper<d(25))return;
        String key=pane==1?"rsi14":pane==2?"adx14":"volume_ratio";
        String label=pane==1?"RSI(14) · 참고지표":pane==2?"ADX(14) · 참고지표":"정규화 거래량 · 전략 진단";
        Map<Long,JSONObject> values=overlays;
        if(pane==3)values=auditValues;
        double ceiling=pane==3?10:100;
        if(pane==3)for(JSONObject row:values.values()){double v=row.optDouble(key,Double.NaN);if(Double.isFinite(v))ceiling=Math.max(ceiling,v);}
        p.setColor(Color.rgb(40,44,52));p.setStrokeWidth(d(1));
        for(int i=0;i<=2;i++){float yy=upper+(lower-upper)*i/2;c.drawLine(left,yy,right,yy,p);}
        if(pane==1){p.setColor(Color.rgb(85,75,45));for(int level:new int[]{30,70}){float yy=lower-(lower-upper)*level/100;c.drawLine(left,yy,right,yy,p);}}
        text(c,label,left,upper+d(10),Color.LTGRAY,10);
        p.setColor(Color.rgb(126,87,194));p.setStrokeWidth(d(1.5f));
        boolean have=false;float px=0,py=0;int valid=0;
        for(int i=0;i<candles.size();i++){
            JSONObject row=values.get((long)candles.get(i)[0]);double v=row==null?Double.NaN:row.optDouble(key,Double.NaN);
            if(!Double.isFinite(v)){have=false;continue;}valid++;
            float xx=left+step*(i+.5f),yy=lower-(float)(v/ceiling)*(lower-upper);
            if(have)c.drawLine(px,py,xx,yy,p);px=xx;py=yy;have=true;
        }
        if(valid==0)text(c,pane==3?"전략 적용 후 표시":"지표 워밍업 데이터 부족",left,upper+d(28),Color.GRAY,10);
    }
}
