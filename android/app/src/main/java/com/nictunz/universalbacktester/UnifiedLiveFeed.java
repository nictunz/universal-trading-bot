package com.nictunz.universalbacktester;

import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.webkit.*;
import android.widget.*;
import android.view.View;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.*;
import java.io.File;
import java.util.concurrent.*;

/** One market subscription for the unified chart; no order or config writes. */
final class UnifiedLiveFeed {
    interface Listener {void changed();void state(JSONObject state,JSONArray trades);void unavailable();}
    private final Activity host;private final Listener listener;private final Handler ui=new Handler(Looper.getMainLooper());
    private final ExecutorService priceWorker=Executors.newSingleThreadExecutor(),serverWorker=Executors.newSingleThreadExecutor();
    private final TextView status;private final WebView login;
    private volatile boolean active,closed,priceBusy,serverBusy;
    private volatile String database="",origin="";
    private volatile SshBridge.DashboardTunnel tunnel;
    private long lastServer,lastPrice,lastTrades;
    private JSONArray history=new JSONArray();
    final String tail;
    private final Runnable tick=new Runnable(){public void run(){if(!active||closed)return;prices();server();ui.postDelayed(this,3000);}};
    UnifiedLiveFeed(Activity host,LinearLayout root,Listener listener){
        this.host=host;this.listener=listener;tail=new File(host.getFilesDir(),"live-btc-15m.sqlite").getAbsolutePath();
        status=new TextView(host);status.setTextColor(Color.CYAN);status.setPadding(12,8,12,8);status.setText("실시간 연결 꺼짐");root.addView(status,3);
        login=new WebView(host);login.setVisibility(View.GONE);login.getSettings().setJavaScriptEnabled(true);login.getSettings().setDomStorageEnabled(true);login.getSettings().setAllowFileAccess(false);login.getSettings().setAllowContentAccess(false);login.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);CookieManager.getInstance().setAcceptCookie(true);
        login.setWebViewClient(new WebViewClient(){public boolean shouldOverrideUrlLoading(WebView w,WebResourceRequest r){return !sameOrigin(r.getUrl());}public void onPageFinished(WebView w,String url){if(sameOrigin(Uri.parse(url))&&"/".equals(Uri.parse(url).getPath())){login.setVisibility(View.GONE);CookieManager.getInstance().flush();server();}}});root.addView(login,4,new LinearLayout.LayoutParams(-1,300));
    }
    private boolean sameOrigin(Uri u){if(origin.isEmpty())return false;Uri b=Uri.parse(origin);return b.getScheme().equals(u.getScheme())&&b.getHost().equals(u.getHost())&&b.getPort()==u.getPort();}
    static Python python(Activity host){synchronized(Python.class){if(!Python.isStarted())Python.start(new AndroidPlatform(host.getApplicationContext()));return Python.getInstance();}}
    void start(String db){if(closed||(active&&database.equals(db)))return;database=db;active=true;ui.removeCallbacks(tick);ui.post(tick);if(origin.isEmpty()&&!serverBusy)connect();}
    void pause(){active=false;ui.removeCallbacks(tick);login.setVisibility(View.GONE);}
    void login(){if(origin.isEmpty()){status.setText("서버 연결 중입니다. 잠시 후 다시 눌러주세요.");if(!serverBusy)connect();return;}login.setVisibility(View.VISIBLE);login.loadUrl(origin+"/login?next=/");}
    private void connect(){serverBusy=true;serverWorker.execute(()->{try{
        android.content.SharedPreferences p=host.getSharedPreferences("universal_bot",0);JSONObject key=new JSONObject(SshBridge.ensureKey(host.getFilesDir().getAbsolutePath()));
        SshBridge.DashboardTunnel opened=SshBridge.openDashboardTunnel(p.getString("relay_host","34.132.172.40").trim(),p.getString("relay_user","kpj3669").trim(),key.getString("private_key"),8000);
        if(closed){opened.close();return;}tunnel=opened;origin="http://127.0.0.1:"+opened.getLocalPort();
    }catch(Exception e){message("서버 연결 실패 · "+e.getMessage());}finally{serverBusy=false;}});}
    private void message(String text){ui.post(()->{if(!closed&&active)status.setText(text);});}
    private void prices(){if(priceBusy||database.isEmpty())return;priceBusy=true;final String source=database;priceWorker.execute(()->{try{
        JSONObject body=LiveMarketChartActivity.get("https://api.bitget.com/api/v2/mix/market/candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=15m&limit=200",null);
        if(!"00000".equals(body.optString("code")))throw new Exception(body.optString("msg","시세 오류"));
        Python py=python(host);long now=body.optLong("requestTime",System.currentTimeMillis());
        py.getModule("universal_bot.live_timeline").callAttr("ingest",tail,body.getJSONArray("data").toString(),now);
        long before=py.getModule("universal_bot.live_timeline").callAttr("gap_before",source,tail).toLong();
        String suffix="";
        if(before>0&&active&&!closed){
            try{JSONObject older=LiveMarketChartActivity.get("https://api.bitget.com/api/v2/mix/market/history-candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=15m&limit=200&endTime="+before,null);
            if(!"00000".equals(older.optString("code")))throw new Exception(older.optString("msg","과거 시세 오류"));
            JSONArray rows=older.getJSONArray("data");py.getModule("universal_bot.live_timeline").callAttr("ingest",tail,rows.toString(),now);
            suffix=rows.length()==0?" · ⚠ 빈 구간 보충 불가":" · 빈 구간 자동 보충 중";}catch(Exception gapError){suffix=" · ⚠ 빈 구간 보충 실패: "+gapError.getMessage();}
        }
        final String info=suffix;ui.post(()->{if(closed||!active||!database.equals(source))return;lastPrice=System.currentTimeMillis();status.setText("시세 수신 · 약 3초 갱신"+info+" · 서버 수신 "+(lastServer==0?"대기":(System.currentTimeMillis()-lastServer)/1000+"초 전"));listener.changed();});
    }catch(Exception e){message("⚠ 시세 갱신 실패 · "+e.getMessage()+" · 마지막 수신 "+(lastPrice==0?"없음":(System.currentTimeMillis()-lastPrice)/1000+"초 전"));}finally{priceBusy=false;}});}
    private void server(){if(serverBusy||origin.isEmpty()||!active)return;serverBusy=true;String base=origin,cookie=CookieManager.getInstance().getCookie(origin);serverWorker.execute(()->{try{
        JSONArray symbols=LiveMarketChartActivity.get(base+"/api/state",cookie).getJSONArray("symbols");JSONObject found=null;
        for(int i=0;i<symbols.length();i++){JSONObject r=symbols.getJSONObject(i);if("BTC/USDT:USDT".equals(r.optString("symbol"))&&"15m".equals(r.optString("timeframe"))){found=r;break;}}
        if(found==null)throw new Exception("서버에 BTC 15분 전략이 없습니다");
        if(System.currentTimeMillis()-lastTrades>15000){lastTrades=System.currentTimeMillis();try{JSONArray rows=LiveMarketChartActivity.get(base+"/api/trades?symbol=BTC%2FUSDT%3AUSDT&timeframe=15m&exchange=bitget&mode=LIVE&limit=100",cookie).optJSONArray("trades");history=rows==null?new JSONArray():rows;}catch(Exception ignored){history=new JSONArray();}}
        final JSONObject state=found;final JSONArray log=history;ui.post(()->{if(!closed&&active){lastServer=System.currentTimeMillis();listener.state(state,log);}});
    }catch(Exception e){ui.post(()->{if(!closed&&active){status.setText("⚠ 서버 조회 실패 · "+e.getMessage());listener.unavailable();}});}finally{serverBusy=false;}});}
    void close(){closed=true;pause();priceWorker.shutdownNow();serverWorker.shutdownNow();if(tunnel!=null)tunnel.close();login.stopLoading();login.destroy();}
}
