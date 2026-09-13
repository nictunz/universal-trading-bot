package com.nictunz.universalbacktester;

import android.content.Context;
import android.graphics.*;
import android.view.*;
import org.json.*;
import java.util.*;

/** Offline OHLC chart. Only the visible window is kept in memory. */
public class CandleChartView extends View {
    public interface Navigator { void move(int bars); void zoom(float factor); void inspect(long timestamp); }
    private final Paint p = new Paint(3);
    private final Navigator nav;
    private final ScaleGestureDetector scale;
    private final GestureDetector gestures;
    private List<double[]> candles = Collections.emptyList();
    private JSONArray trades = new JSONArray();
    private JSONArray audit = new JSONArray();
    public void setAudit(JSONArray rows){audit=rows==null?new JSONArray():rows;invalidate();}
    private int selected = -1;
    private double min, max;
    private float left, right, top, bottom, step;
    private float drag;
    private static final int UP = Color.rgb(38,166,154), DOWN = Color.rgb(239,83,80);
    public CandleChartView(Context c, Navigator n) {
        super(c); nav=n; setBackgroundColor(Color.rgb(16,19,24));
        scale=new ScaleGestureDetector(c,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            public boolean onScale(ScaleGestureDetector d){ nav.zoom(d.getScaleFactor()); return true; }
        });
        gestures=new GestureDetector(c,new GestureDetector.SimpleOnGestureListener(){
            public boolean onDown(MotionEvent e){drag=0; return true;}
            public boolean onScroll(MotionEvent a,MotionEvent b,float dx,float dy){
                if(scale.isInProgress()) return true;
                selected=-1; drag+=dx/Math.max(1,step);
                if(Math.abs(drag)>=2){int count=(int)drag; drag-=count; nav.move(count);} return true;
            }
            public boolean onSingleTapUp(MotionEvent e){ select(e.getX()); performClick(); return true; }
            public void onLongPress(MotionEvent e){select(e.getX());}
        });
    }
    public void setData(List<double[]> data,JSONArray log){candles=data; trades=log; selected=-1; invalidate();}
    private void select(float x){if(candles.isEmpty())return;selected=Math.max(0,Math.min(candles.size()-1,(int)((x-left)/Math.max(1,step))));nav.inspect((long)candles.get(selected)[0]);invalidate();}
    @Override public boolean performClick(){super.performClick();return true;}
    @Override public boolean onTouchEvent(MotionEvent e){
        getParent().requestDisallowInterceptTouchEvent(true);
        scale.onTouchEvent(e); gestures.onTouchEvent(e); return true;
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
        super.onDraw(c);left=d(8);right=getWidth()-d(82);top=d(50);bottom=getHeight()-d(78);
        if(candles.isEmpty()){text(c,"DB를 선택하세요",d(16),d(40),Color.LTGRAY,14);return;}
        step=(right-left)/candles.size();min=Double.POSITIVE_INFINITY;max=Double.NEGATIVE_INFINITY;double vmax=1;
        for(double[] b:candles){min=Math.min(min,b[3]);max=Math.max(max,b[2]);vmax=Math.max(vmax,b[5]);}
        double pad=Math.max((max-min)*.08,Math.abs(max)*.0001);min-=pad;max+=pad;
        p.setStrokeWidth(d(1));
        for(int i=0;i<=5;i++){float yy=top+(bottom-top)*i/5;p.setColor(Color.rgb(40,44,52));c.drawLine(left,yy,right,yy,p);text(c,number(max-(max-min)*i/5),right+d(4),yy,Color.LTGRAY,10);}
        for(int i=0;i<=6;i++){float xx=left+(right-left)*i/6;p.setColor(Color.rgb(32,36,42));c.drawLine(xx,top,xx,bottom+d(48),p);}
        for(int i=0;i<candles.size();i++){
            double[] b=candles.get(i);float x=left+step*(i+.5f);int col=b[4]>=b[1]?UP:DOWN;
            p.setColor(col);p.setStrokeWidth(Math.max(1,d(.8f)));c.drawLine(x,y(b[2]),x,y(b[3]),p);
            c.drawRect(x-Math.max(.6f,step*.32f),Math.min(y(b[1]),y(b[4])),x+Math.max(.6f,step*.32f),Math.max(y(b[1]),y(b[4]))+1,p);
            p.setAlpha(90);c.drawRect(x-step*.32f,bottom+d(48)-(float)(b[5]/vmax)*d(40),x+step*.32f,bottom+d(48),p);p.setAlpha(255);
        }
        c.save();c.clipRect(left,top,right,bottom);
        for(int j=0;j<trades.length();j++){
            JSONObject t=trades.optJSONObject(j);if(t==null)continue;
            long en=millis(t.optString("entry_time")),ex=millis(t.optString("exit_time"));
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
            boolean recorded=false;
            for(int k=0;k<trades.length();k++){JSONObject t=trades.optJSONObject(k);if(t!=null&&millis(t.optString("entry_time"))==r.optLong("timestamp")){recorded=true;break;}}
            if(r.optBoolean("entry")&&!recorded)text(c,"◆ "+r.optString("position")+" 진입",left+step*(at+.5f),y(candles.get(at)[4])-d(10),Color.CYAN,10);
            // The trace also contains still-open positions absent from closed trades.
            double tp=r.optDouble("tp",Double.NaN),sl=r.optDouble("sl",Double.NaN);
            for(double price:new double[]{tp,sl}){
                if(!Double.isFinite(price)||price<min||price>max)continue;
                p.setColor(price==tp?UP:DOWN);p.setStrokeWidth(d(1));
                c.drawLine(left+step*at,y(price),left+step*(at+1),y(price),p);
            }
        }
        c.restore();
        int k=selected>=0?selected:candles.size()-1;double[] b=candles.get(k);
        text(c,"O "+number(b[1])+"  H "+number(b[2])+"  L "+number(b[3]),d(8),d(18),Color.LTGRAY,11);
        text(c,"C "+number(b[4])+"  V "+number(b[5])+"  "+time((long)b[0])+" UTC",d(8),d(35),b[4]>=b[1]?UP:DOWN,11);
        if(selected>=0){float x=left+step*(selected+.5f);p.setColor(Color.GRAY);p.setPathEffect(new DashPathEffect(new float[]{d(4),d(4)},0));c.drawLine(x,top,x,bottom,p);c.drawLine(left,y(b[4]),right,y(b[4]),p);p.setPathEffect(null);}
        text(c,time((long)candles.get(0)[0]),left,getHeight()-d(12),Color.GRAY,10);
        text(c,time((long)candles.get(candles.size()-1)[0]),Math.max(left,right-d(96)),getHeight()-d(12),Color.GRAY,10);
    }
}
