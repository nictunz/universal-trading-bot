package com.nictunz.universalbacktester;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.*;
import android.webkit.CookieManager;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;

/** Read-only live market view. Never sends orders or changes server configuration. */
public class LiveMarketChartActivity extends Activity implements CandleChartView.Navigator {
    private final Handler ui=new Handler(Looper.getMainLooper());
    private final ExecutorService prices=Executors.newSingleThreadExecutor(),server=Executors.newSingleThreadExecutor();
    private volatile boolean disposed,resumed,priceBusy,serverBusy;
    private volatile String origin="";
    private volatile SshBridge.DashboardTunnel tunnel;
    private CandleChartView chart;
    private TextView priceStatus,serverStatus,diagnostic;
    private WebView login;
    private final TreeMap<Long,double[]> candles=new TreeMap<>();
    private JSONArray trades=new JSONArray();
    private int width=100,end=0;
    private boolean follow=true;
    private long priceReceived,serverReceived,lastTrades;
    private final Runnable tick=new Runnable(){public void run(){if(!resumed||disposed)return;pollPrice();pollServer();ui.postDelayed(this,3000);}};
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private void button(LinearLayout row,String text,Runnable action){Button b=new Button(this);b.setText(text);b.setAllCaps(false);b.setOnClickListener(v->action.run());row.addView(b,new LinearLayout.LayoutParams(0,dp(48),1));}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        LinearLayout root=new LinearLayout(this);root.setOrientation(1);root.setBackgroundColor(Color.rgb(16,19,24));
        LinearLayout controls=new LinearLayout(this);
        button(controls,"‹ DB",this::finish);button(controls,"최신 따라가기",()->{follow=true;draw();});button(controls,"서버 로그인",this::showLogin);root.addView(controls);
        priceStatus=label(root,"LIVE 시세 · BITGET BTCUSDT · 15분 · 연결 중",Color.CYAN);
        serverStatus=label(root,"서버 신호 · SSH 연결 중",Color.LTGRAY);
        diagnostic=label(root,"현재 봉은 미확정입니다. 확정 신호·포지션은 서버 수신 후 표시합니다.",Color.LTGRAY);
        chart=new CandleChartView(this,this);chart.options(false,false,0);root.addView(chart,new LinearLayout.LayoutParams(-1,0,1));
        login=new WebView(this);login.setVisibility(View.GONE);login.getSettings().setJavaScriptEnabled(true);login.getSettings().setDomStorageEnabled(true);login.getSettings().setAllowFileAccess(false);login.getSettings().setAllowContentAccess(false);login.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);CookieManager.getInstance().setAcceptCookie(true);
        login.setWebViewClient(new WebViewClient(){
            public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return !sameOrigin(request.getUrl());}
            public void onPageFinished(WebView view,String url){Uri uri=Uri.parse(url);if(sameOrigin(uri)&&"/".equals(uri.getPath())){CookieManager.getInstance().flush();login.setVisibility(View.GONE);chart.setVisibility(View.VISIBLE);pollServer();}}
        });root.addView(login,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);connect();
    }
    private TextView label(LinearLayout root,String value,int color){TextView t=new TextView(this);t.setText(value);t.setTextColor(color);t.setTextSize(12);t.setPadding(dp(10),dp(5),dp(10),dp(5));root.addView(t);return t;}
    private boolean sameOrigin(Uri u){if(origin.isEmpty())return false;Uri base=Uri.parse(origin);return base.getScheme().equals(u.getScheme())&&base.getHost().equals(u.getHost())&&base.getPort()==u.getPort();}
    private void showLogin(){if(origin.isEmpty()){serverStatus.setText("SSH 연결을 준비 중입니다. 연결 실패 시 화면을 다시 열어주세요.");return;}login.setVisibility(View.VISIBLE);chart.setVisibility(View.GONE);login.loadUrl(origin+"/login?next=/");}
    private void connect(){server.execute(()->{try{
        android.content.SharedPreferences prefs=getSharedPreferences("universal_bot",MODE_PRIVATE);
        JSONObject key=new JSONObject(SshBridge.ensureKey(getFilesDir().getAbsolutePath()));
        SshBridge.DashboardTunnel opened=SshBridge.openDashboardTunnel(prefs.getString("relay_host","34.132.172.40").trim(),prefs.getString("relay_user","kpj3669").trim(),key.getString("private_key"),8000);
        if(disposed){opened.close();return;}tunnel=opened;origin="http://127.0.0.1:"+opened.getLocalPort();
        ui.post(()->{if(!disposed){serverStatus.setText("서버 연결됨 · 신호 조회 중");pollServer();}});
    }catch(Exception e){showServerError("SSH 연결 실패: "+e.getMessage());}});}
    private static JSONObject get(String url,String cookie)throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();c.setConnectTimeout(7000);c.setReadTimeout(7000);c.setInstanceFollowRedirects(false);c.setRequestProperty("Accept","application/json");if(cookie!=null&&!cookie.isEmpty())c.setRequestProperty("Cookie",cookie);
        try{int status=c.getResponseCode();if(status==401||status==403||status==302||status==303)throw new IOException("인증 필요 · 서버 로그인 버튼을 누르세요");if(status!=200)throw new IOException("HTTP "+status);
            try(InputStream input=c.getInputStream();ByteArrayOutputStream output=new ByteArrayOutputStream()){byte[] buffer=new byte[8192];int n;while((n=input.read(buffer))!=-1){if(output.size()+n>2*1024*1024)throw new IOException("응답 크기 초과");output.write(buffer,0,n);}return new JSONObject(output.toString("UTF-8"));}
        }finally{c.disconnect();}
    }
    private void pollPrice(){if(priceBusy||disposed||!resumed)return;priceBusy=true;prices.execute(()->{try{
        JSONObject body=get("https://api.bitget.com/api/v2/mix/market/candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=15m&limit=200",null);
        if(!"00000".equals(body.optString("code")))throw new IOException(body.optString("msg","거래소 오류"));
        JSONArray data=body.getJSONArray("data");TreeMap<Long,double[]> rows=new TreeMap<>();
        for(int i=0;i<data.length();i++){JSONArray a=data.getJSONArray(i);double[] b=new double[6];for(int k=0;k<6;k++)b[k]=a.getDouble(k);if(b[0]<=0||b[1]<=0||b[3]<=0||b[2]<Math.max(b[1],b[4])||b[3]>Math.min(b[1],b[4])||b[5]<0)throw new IOException("잘못된 캔들 응답");for(double v:b)if(!Double.isFinite(v))throw new IOException("잘못된 캔들 값");rows.put((long)b[0],b);}
        if(rows.isEmpty())throw new IOException("시세 데이터 없음");
        long exchangeTime=body.optLong("requestTime",System.currentTimeMillis());
        ui.post(()->{if(disposed||!resumed)return;candles.putAll(rows);while(candles.size()>1000)candles.pollFirstEntry();priceReceived=System.currentTimeMillis();double[] last=rows.lastEntry().getValue();boolean forming=exchangeTime<(long)last[0]+900000L;boolean stale=exchangeTime-(long)last[0]>1800000L;
            priceStatus.setText("LIVE · BITGET BTC · 15분 · "+last[4]+" · "+(stale?"⚠ 시세 지연":forming?"진행봉 · 확정 신호 아님":"최근 확정봉")+" · 수신 "+clock(priceReceived));draw();});
    }catch(Exception e){ui.post(()->{if(!disposed&&resumed)priceStatus.setText("⚠ 시세 갱신 실패 · "+e.getMessage()+" · 마지막 수신 "+clock(priceReceived));});}finally{priceBusy=false;}});}
    private void pollServer(){if(serverBusy||origin.isEmpty()||disposed||!resumed)return;serverBusy=true;final String base=origin,cookie=CookieManager.getInstance().getCookie(base);server.execute(()->{try{
        JSONObject body=get(base+"/api/state",cookie),found=null;JSONArray symbols=body.getJSONArray("symbols");for(int i=0;i<symbols.length();i++){JSONObject row=symbols.getJSONObject(i);if("BTC/USDT:USDT".equals(row.optString("symbol"))&&"15m".equals(row.optString("timeframe"))){found=row;break;}}
        if(found==null)throw new IOException("서버에 BTC 15분 전략이 없습니다");final JSONObject state=found;
        ui.post(()->{if(disposed||!resumed)return;serverReceived=System.currentTimeMillis();renderState(state);});
        if(System.currentTimeMillis()-lastTrades>15000){lastTrades=System.currentTimeMillis();try{
            JSONObject history=get(base+"/api/trades?symbol=BTC%2FUSDT%3AUSDT&timeframe=15m&exchange=bitget&mode=LIVE&limit=100",cookie);JSONArray log=history.optJSONArray("trades");
            ui.post(()->{if(!disposed&&resumed){trades=log==null?new JSONArray():log;draw();}});
        }catch(Exception historyError){ui.post(()->{if(!disposed&&resumed)serverStatus.append(" · 체결 이력 조회 실패");});}}
    }catch(Exception e){showServerError(e.getMessage());}finally{serverBusy=false;}});}
    private void renderState(JSONObject state){
        JSONObject v=state.optJSONObject("values"),position=state.optJSONObject("position"),safety=state.optJSONObject("live_safety");if(v==null)v=new JSONObject();if(position==null)position=new JSONObject();if(safety==null)safety=new JSONObject();
        String timestamp=state.optString("timestamp",""),signal=state.isNull("signal")?"없음":state.optString("signal","없음");long signalTime=CandleChartView.millis(timestamp);boolean stale=signalTime<0||System.currentTimeMillis()-signalTime>35*60*1000L;
        serverStatus.setText((stale?"⚠ 서버 데이터 지연":"서버 수신 "+clock(serverReceived))+" · 중계 요청 "+(getSharedPreferences("universal_bot",MODE_PRIVATE).getBoolean("relay_requested",false)?"켜짐":"꺼짐")+" · "+(safety.optBoolean("halted")?"거래 중단":"상태 수신"));
        JSONObject exchange=safety.optJSONObject("exchange_position");String actual=exchange==null?"미확인":exchange.optString("side","미확인")+" / "+exchange.optDouble("size",0);
        diagnostic.setText("서버 판정봉 UTC "+timestamp+"\n확정 신호: "+signal+" · "+state.optString("signal_reason","")+"\n거래량 ×"+v.optString("volume_ratio","—")+" · RSI "+v.optString("rsi","—")+" · ADX "+v.optString("adx","—")+"\n거래소 포지션: "+actual+" · 대조 "+safety.optString("last_reconciliation","미확인")+"\n서버 TP "+position.optString("tp","—")+" / SL "+position.optString("sl","—")+"\n4거래소: "+sourceStatus(state.optJSONObject("volume_sources"))+(state.optString("error","").isEmpty()?"":"\n오류: "+state.optString("error")));
        chart.setLivePosition(stale?new JSONObject():position);
    }
    private void showServerError(String error){ui.post(()->{if(!disposed&&resumed){serverStatus.setText("⚠ 서버 조회 실패 · "+error+" · 마지막 수신 "+clock(serverReceived));chart.setLivePosition(new JSONObject());diagnostic.setText("서버 신호·포지션 최신 여부를 확인할 수 없습니다.\n공개 시세와 서버 연결은 별도입니다.");}});}
    private static String sourceStatus(JSONObject sources){if(sources==null)return "미확인";StringBuilder text=new StringBuilder();for(String name:new String[]{"binance","bitget","okx","bybit"}){JSONObject row=sources.optJSONObject(name);if(text.length()>0)text.append(" · ");text.append(name).append(":").append(row==null?"미확인":row.optString("status","미확인"));}return text.toString();}
    private static String clock(long time){if(time==0)return "없음";java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("HH:mm:ss",Locale.US);return f.format(new Date(time));}
    private void draw(){if(candles.isEmpty())return;ArrayList<double[]> all=new ArrayList<>(candles.values());if(follow)end=all.size();end=Math.max(1,Math.min(end,all.size()));chart.setData(new ArrayList<>(all.subList(Math.max(0,end-width),end)),trades);}
    public void move(int bars){follow=false;end=Math.max(Math.min(width,candles.size()),Math.min(candles.size(),end+bars));draw();}
    public void zoom(float factor){width=Math.max(30,Math.min(200,(int)(width/factor)));draw();}
    public void inspect(long timestamp){} public void drawing(JSONObject shape){}
    @Override protected void onResume(){super.onResume();resumed=true;ui.removeCallbacks(tick);ui.post(tick);}
    @Override protected void onPause(){resumed=false;ui.removeCallbacks(tick);super.onPause();}
    @Override public void onBackPressed(){if(login.getVisibility()==View.VISIBLE){login.setVisibility(View.GONE);chart.setVisibility(View.VISIBLE);}else super.onBackPressed();}
    @Override protected void onDestroy(){disposed=true;resumed=false;ui.removeCallbacksAndMessages(null);prices.shutdownNow();server.shutdownNow();if(tunnel!=null)tunnel.close();login.stopLoading();login.destroy();super.onDestroy();}
}
