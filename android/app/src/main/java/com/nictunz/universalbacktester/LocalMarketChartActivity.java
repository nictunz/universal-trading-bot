package com.nictunz.universalbacktester;

import android.app.*;
import android.content.Intent;
import android.content.DialogInterface;
import android.net.Uri;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import android.os.Bundle;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.graphics.Color;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Read-only, paged SQLite candles, available before any backtest is run. */
public class LocalMarketChartActivity extends Activity implements CandleChartView.Navigator {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final AtomicInteger generation=new AtomicInteger();
    private final ArrayList<String[]> markets=new ArrayList<>();
    private final ArrayList<String[]> allMarkets=new ArrayList<>();
    private final ArrayList<File> databaseFiles=new ArrayList<>();
    private CandleChartView chart;
    private TextView status;
    private Spinner selector;
    private Button databaseSelector;
    private String[] market;
    private String selectedDatabasePath="";
    private int total,offset,width=160;
    private JSONArray trades=new JSONArray();
    private String resultPath="";
    private boolean disposed;
    private String loadedResultPath;
    private long loadedResultModified;
    private JSONObject loadedResult = new JSONObject();
    private float zoomWidth=160;
    private TextView diagnostic, warning;
    private JSONObject auditPage = new JSONObject();
    private String strategyParameters = "";
    private volatile boolean busy;
    private String exportPath = "";
    private File cancelFile;
    private long inspectedTime;
    private static final int IMPORT_DB=8201, EXPORT_DB=8202, IMPORT_JSON=8203;
    private Python python() {
        if(!Python.isStarted()) Python.start(new AndroidPlatform(this));
        return Python.getInstance();
    }
    private boolean blocked() {
        if(busy || BacktestForegroundService.isWorkerRunning()){
            status.setText("실행 중인 작업을 마친 뒤 DB 관리·전략 적용을 진행하세요.");return true;
        }
        return false;
    }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        strategyParameters=getIntent().getStringExtra("strategy_parameters");
        if(strategyParameters==null)strategyParameters="";
        resultPath=getIntent().getStringExtra("result_path");
        if(resultPath==null)resultPath="";
        String requested=getIntent().getStringExtra("db_path");
        if(requested==null||requested.isEmpty())requested=getSharedPreferences("universal_bot",MODE_PRIVATE).getString("chart_db_path","");
        selectedDatabasePath=requested==null?"":requested;
        LinearLayout root=new LinearLayout(this);root.setOrientation(1);root.setBackgroundColor(Color.rgb(16,19,24));
        LinearLayout bar=new LinearLayout(this);
        Button back=new Button(this);back.setText("‹");back.setOnClickListener(v->finish());bar.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));
        databaseSelector=new Button(this);databaseSelector.setAllCaps(false);databaseSelector.setText("DB 선택");databaseSelector.setOnClickListener(v->showDatabasePicker());bar.addView(databaseSelector,new LinearLayout.LayoutParams(dp(132),dp(48)));
        selector=new Spinner(this);bar.addView(selector,new LinearLayout.LayoutParams(0,dp(48),1));
        selector.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> p){}
            public void onItemSelected(AdapterView<?> p,View v,int pos,long id){
                if(pos<0||pos>=markets.size())return;
                if(busy)return;
                market=markets.get(pos);total=Integer.parseInt(market[4]);offset=Math.max(0,total-width);trades=new JSONArray();load();
            }
        });
        root.addView(bar);
        status=new TextView(this);status.setTextColor(Color.LTGRAY);status.setTextSize(12);status.setPadding(dp(10),0,dp(10),0);status.setText("저장된 코인 DB 검색 중…");root.addView(status);
        warning=new TextView(this);warning.setTextColor(Color.rgb(255,190,75));warning.setTextSize(12);warning.setPadding(dp(10),dp(4),dp(10),dp(4));root.addView(warning);
        diagnostic=new TextView(this);diagnostic.setTextColor(Color.LTGRAY);diagnostic.setTextSize(12);diagnostic.setMaxLines(4);diagnostic.setPadding(dp(10),dp(4),dp(10),dp(4));diagnostic.setText("전략 적용 후 봉을 터치하면 실제 엔진 진단이 표시됩니다.");diagnostic.setOnClickListener(v->showDiagnostic());root.addView(diagnostic);
        chart=new CandleChartView(this,this);root.addView(chart,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout actions=new LinearLayout(this);
        addButton(actions,"날짜",()->{Calendar now=Calendar.getInstance();new DatePickerDialog(this,(v,y,m,d)->jumpDate(y,m,d),now.get(Calendar.YEAR),now.get(Calendar.MONTH),now.get(Calendar.DAY_OF_MONTH)).show();});
        addButton(actions,"최근",()->{offset=Math.max(0,total-width);load();});
        addButton(actions,"거래",this::showTrades);
        addButton(actions,"결과",this::chooseResult);
        root.addView(actions);
        LinearLayout workspace=new LinearLayout(this);
        addButton(workspace,"DB 관리",this::manageDatabase);
        addButton(workspace,"전략 적용",this::strategyDialog);
        addButton(workspace,"진단",this::showDiagnostic);
        root.addView(workspace);setContentView(root);
        scanDatabases();
    }
    private void scanDatabases(){
        generation.incrementAndGet();
        worker.execute(()->{
            ArrayList<File> dbs=new ArrayList<>();collect(new File(getFilesDir(),"UniversalTradingBotCache"),".db",dbs,4);
            File requestedFile=selectedDatabasePath.isEmpty()?null:new File(selectedDatabasePath);
            if(requestedFile!=null&&requestedFile.isFile()&&!containsPath(dbs,requestedFile))dbs.add(0,requestedFile);
            ArrayList<String[]> found=new ArrayList<>();
            for(File file:dbs){
                try(SQLiteDatabase db=SQLiteDatabase.openDatabase(file.getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY);
                    Cursor c=db.rawQuery("SELECT exchange,symbol,timeframe,count(*) FROM ohlcv WHERE asset_class='crypto' GROUP BY exchange,symbol,timeframe ORDER BY CASE WHEN exchange='bitget' THEN 0 ELSE 1 END",null)){
                    while(c.moveToNext())found.add(new String[]{file.getAbsolutePath(),c.getString(0),c.getString(1),c.getString(2),c.getString(3)});
                }catch(Exception ignored){}
            }
            runOnUiThread(()->{
                if(disposed)return;
                allMarkets.clear();allMarkets.addAll(found);databaseFiles.clear();
                for(String[] row:allMarkets){File file=new File(row[0]);if(!containsPath(databaseFiles,file))databaseFiles.add(file);}
                if(databaseFiles.isEmpty()){market=null;total=0;trades=new JSONArray();chart.setData(Collections.emptyList(),trades);databaseSelector.setText("DB 선택");status.setText("DB 관리 → 파일 불러오기 또는 백테스터에서 DB를 다운로드하세요.");return;}
                File initial=null;for(File file:databaseFiles)if(samePath(file.getAbsolutePath(),selectedDatabasePath)){initial=file;break;}
                selectDatabase(initial==null?databaseFiles.get(0):initial);
            });
        });
    }
    private void addButton(LinearLayout row,String label,Runnable action){Button b=new Button(this);b.setText(label);b.setOnClickListener(v->action.run());row.addView(b,new LinearLayout.LayoutParams(0,dp(48),1));}
    private int dp(int n){return (int)(n*getResources().getDisplayMetrics().density);}
    private static void collect(File dir,String suffix,List<File> out,int depth){if(depth<0)return;File[] fs=dir.listFiles();if(fs==null)return;for(File f:fs){if(f.isDirectory())collect(f,suffix,out,depth-1);else if(f.getName().toLowerCase(Locale.US).endsWith(suffix))out.add(f);}}
    private static boolean samePath(String left,String right){return left!=null&&!left.isEmpty()&&right!=null&&!right.isEmpty()&&new File(left).getAbsolutePath().equals(new File(right).getAbsolutePath());}
    private static boolean containsPath(List<File> files,File target){if(target==null)return false;for(File file:files)if(samePath(file.getAbsolutePath(),target.getAbsolutePath()))return true;return false;}
    private String readableBytes(long bytes){if(bytes>=1_000_000_000L)return String.format(Locale.US,"%.1f GB",bytes/1_000_000_000.0);if(bytes>=1_000_000L)return String.format(Locale.US,"%.1f MB",bytes/1_000_000.0);return String.format(Locale.US,"%.1f KB",bytes/1_000.0);}
    private void selectDatabase(File database){
        if(database==null||blocked())return;
        generation.incrementAndGet();
        auditPage=new JSONObject();
        chart.setData(Collections.emptyList(),new JSONArray());chart.setAudit(null);
        diagnostic.setText("전략 적용 또는 저장 결과 선택 후 진단을 확인하세요.");
        selectedDatabasePath=database.getAbsolutePath();
        resultPath=getSharedPreferences("universal_bot",MODE_PRIVATE).getString("chart_result:"+selectedDatabasePath,resultPath);
        strategyParameters=getSharedPreferences("universal_bot",MODE_PRIVATE).getString("chart_parameters:"+selectedDatabasePath,strategyParameters);
        getSharedPreferences("universal_bot",MODE_PRIVATE).edit().putString("chart_db_path",selectedDatabasePath).apply();
        databaseSelector.setText("DB · "+database.getName());
        markets.clear();for(String[] row:allMarkets)if(samePath(row[0],selectedDatabasePath))markets.add(row);
        market=null;total=0;offset=0;trades=new JSONArray();
        ArrayList<String> labels=new ArrayList<>();for(String[] row:markets)labels.add(row[2]+" · "+row[1]+" · "+row[3]);
        selector.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));
        if(markets.isEmpty()){status.setText("선택한 DB에 암호화폐 캔들 데이터가 없습니다.");return;}
        status.setText("DB: "+database.getName()+" · 차트 시장을 선택하세요.");selector.setSelection(0);
    }
    private void showDatabasePicker(){
        if(blocked())return;
        if(databaseFiles.isEmpty()){new AlertDialog.Builder(this).setMessage("선택할 DB가 없습니다. 백테스터에서 DB를 먼저 다운로드하세요.").setPositiveButton("확인",null).show();return;}
        final ArrayList<File> choices=new ArrayList<>(databaseFiles);String[] labels=new String[choices.size()];int checked=0;
        for(int i=0;i<choices.size();i++){File file=choices.get(i);int marketCount=0;for(String[] row:allMarkets)if(samePath(row[0],file.getAbsolutePath()))marketCount++;if(samePath(file.getAbsolutePath(),selectedDatabasePath))checked=i;labels[i]=file.getName()+" · "+readableBytes(file.length())+" · "+marketCount+"개 시장";}
        new AlertDialog.Builder(this).setTitle("차트 DB 선택").setSingleChoiceItems(labels,checked,(dialog,which)->{selectDatabase(choices.get(which));dialog.dismiss();}).setNegativeButton("닫기",null).show();
    }
    private static JSONObject readResult(String path)throws Exception{
        if(path==null||path.isEmpty())return new JSONObject();
        File f=new File(path);if(!f.isFile()||f.length()>64L*1024*1024)throw new IOException("결과 파일을 읽을 수 없습니다.");
        StringBuilder b=new StringBuilder();try(Reader r=new InputStreamReader(new FileInputStream(f),"UTF-8")){char[] buf=new char[8192];int n;while((n=r.read(buf))>=0)b.append(buf,0,n);}
        JSONObject root=new JSONObject(b.toString());JSONObject summary=root.optJSONObject("summary");return summary==null?root:summary;
    }
    private static boolean matches(JSONObject s,String[] m){
        String db=s.optString("cache_database",s.optString("database",""));
        return s.optString("symbol").equals(m[2])&&s.optString("timeframe").equals(m[3])
            &&s.optString("exchange","bitget").equals(m[1])&&!db.isEmpty()&&new File(db).equals(new File(m[0]));
    }
    private void load(){
        if(market==null||disposed||busy)return;
        int request=generation.incrementAndGet();String[] m=market.clone();int start=offset,count=width;String file=resultPath;
        worker.execute(()->{
            if(request!=generation.get())return;
            try(SQLiteDatabase db=SQLiteDatabase.openDatabase(m[0],null,SQLiteDatabase.OPEN_READONLY)){
                ArrayList<double[]> rows=new ArrayList<>();
                try(Cursor c=db.rawQuery("SELECT timestamp,open,high,low,close,volume FROM ohlcv WHERE asset_class='crypto' AND exchange=? AND symbol=? AND timeframe=? ORDER BY timestamp LIMIT ? OFFSET ?",new String[]{m[1],m[2],m[3],""+count,""+start})){
                    while(c.moveToNext()){double[] b=new double[6];for(int i=0;i<6;i++)b[i]=c.getDouble(i);rows.add(b);}
                }
                long modified=file==null?0:new File(file).lastModified();
                if(!Objects.equals(file,loadedResultPath)||modified!=loadedResultModified){
                    try {loadedResult=readResult(file);} catch(Exception unavailable){loadedResult=new JSONObject();}
                    loadedResultPath=file;loadedResultModified=modified;
                }
                JSONObject s=loadedResult;boolean match=matches(s,m);
                JSONObject page=new JSONObject();String alert="";
                if(!m[1].equals("bitget"))alert="⚠ 전략 OHLC 기준은 BITGET입니다. 현재 "+m[1]+" 캔들입니다.";
                else if(match && s.has("chart_audit_database") && !rows.isEmpty()){
                    try{page=new JSONObject(python().getModule("universal_bot.chart_workspace").callAttr("audit_page",file,(long)rows.get(0)[0],(long)rows.get(rows.size()-1)[0]).toString());}
                    catch(Exception e){match=false;alert="⚠ "+e.getMessage();}
                }else alert=match?"⚠ 이전 결과는 봉별 진단이 없습니다. 전략을 다시 적용하세요.":"⚠ 전략 미적용 · 캔들 데이터만 표시합니다.";
                long interval=intervalMillis(m[3]);
                for(int k=0;k<rows.size();k++){
                    double[] bar=rows.get(k);
                    if(bar[1]<=0||bar[2]<bar[3]||bar[2]<Math.max(bar[1],bar[4])||bar[3]>Math.min(bar[1],bar[4]))alert+="\n⚠ 잘못된 OHLC 데이터";
                    if(k>0&&interval>0&&(long)(bar[0]-rows.get(k-1)[0])!=interval){alert+="\n⚠ 표시 구간에 캔들 누락/중복";break;}
                }
                final JSONObject shownPage=page;final String shownAlert=alert;
                JSONArray log=match?s.optJSONArray("trades_log"):null;
                JSONArray data=log==null?new JSONArray():log;
                String msg=match?String.format(Locale.US,"수익 %.2f%% · MDD %.2f%% · %d거래",s.optDouble("return_percent"),s.optDouble("max_drawdown_percent"),data.length()):"캔들 보기 · ‘결과’에서 이 DB의 백테스트를 선택하세요";
                if(data.length()>0&&!data.optJSONObject(0).has("tp_price"))msg+=" · TP/SL 선은 재실행 후 표시";
                final String message=msg;
                runOnUiThread(()->{if(disposed||request!=generation.get())return;trades=data;auditPage=shownPage;warning.setText(shownAlert);chart.setData(rows,data);chart.setAudit(shownPage.optJSONArray("rows"));if(!rows.isEmpty())inspect((long)rows.get(rows.size()-1)[0]);status.setText(message+"\n드래그 이동 · 두 손가락 확대 · 터치 OHLC · UTC");});
            }catch(Exception e){runOnUiThread(()->{if(!disposed&&request==generation.get()){trades=new JSONArray();auditPage=new JSONObject();chart.setData(Collections.emptyList(),trades);chart.setAudit(null);status.setText("차트 읽기 실패: "+e.getMessage());}});}
        });
    }
    @Override public void move(int bars){offset=Math.max(0,Math.min(Math.max(0,total-width),offset+bars));load();}
    @Override public void zoom(float factor){zoomWidth=Math.max(30,Math.min(600,zoomWidth/factor));int next=(int)zoomWidth;if(next==width)return;int center=offset+width/2;width=next;offset=Math.max(0,Math.min(Math.max(0,total-width),center-width/2));load();}
    private void jumpDate(int y,int month,int day){Calendar c=Calendar.getInstance(TimeZone.getTimeZone("UTC"));c.clear();c.set(y,month,day);jump(c.getTimeInMillis());}
    private void jump(long ms){
        if(market==null)return;String[] m=market.clone();int request=generation.incrementAndGet();
        worker.execute(()->{try(SQLiteDatabase db=SQLiteDatabase.openDatabase(m[0],null,SQLiteDatabase.OPEN_READONLY);Cursor c=db.rawQuery("SELECT count(*) FROM ohlcv WHERE asset_class='crypto' AND exchange=? AND symbol=? AND timeframe=? AND timestamp<?",new String[]{m[1],m[2],m[3],""+ms})){
            c.moveToFirst();int n=c.getInt(0);runOnUiThread(()->{if(disposed||request!=generation.get())return;offset=Math.max(0,Math.min(Math.max(0,total-width),n-width/3));load();});
        }catch(Exception e){runOnUiThread(()->{if(!disposed)status.setText("날짜 이동 실패: "+e.getMessage());});}});
    }
    private void showTrades(){
        showTradePage(0);
    }
    private void showTradePage(int start){
        if(trades.length()==0){new AlertDialog.Builder(this).setMessage("선택한 DB의 백테스트 결과를 먼저 선택하세요.").setPositiveButton("확인",null).show();return;}
        HorizontalScrollView horizontal=new HorizontalScrollView(this);
        ScrollView vertical=new ScrollView(this);TableLayout table=new TableLayout(this);table.setBackgroundColor(Color.rgb(16,19,24));
        vertical.addView(table);horizontal.addView(vertical);
        TableRow header=new TableRow(this);
        for(String title:new String[]{"# / 방향","진입 UTC","청산 UTC","진입가","청산가","고정 TP","고정 SL","순손익 USDT","사유"})cell(header,title,true);
        table.addView(header);
        for(int i=start;i<Math.min(trades.length(),start+200);i++){
            JSONObject t=trades.optJSONObject(i);if(t==null)continue;
            TableRow row=new TableRow(this);
            for(String value:new String[]{"#"+(i+1)+" "+t.optString("side"),t.optString("entry_time"),t.optString("exit_time"),num(t,"avg_entry_price"),num(t,"exit_price"),num(t,"tp_price"),num(t,"sl_price"),num(t,"pnl"),t.optString("reason")})cell(row,value,false);
            row.setOnClickListener(v->new AlertDialog.Builder(this).setTitle("거래 캔들로 이동")
                .setItems(new String[]{"진입 봉","청산 봉"},(d,k)->jump(CandleChartView.millis(t.optString(k==0?"entry_time":"exit_time")))).show());
            table.addView(row);
        }
        AlertDialog.Builder dialog=new AlertDialog.Builder(this).setTitle("진입·청산 표 · "+(start+1)+"~"+Math.min(trades.length(),start+200)).setView(horizontal).setNegativeButton("닫기",null);
        if(start>0)dialog.setNeutralButton("이전",(d,i)->showTradePage(Math.max(0,start-200)));
        if(start+200<trades.length())dialog.setPositiveButton("다음",(d,i)->showTradePage(start+200));
        dialog.show();
    }
    private void cell(TableRow row,String value,boolean heading){TextView t=new TextView(this);t.setText(value);t.setTextSize(12);t.setTextColor(heading?Color.CYAN:Color.WHITE);t.setPadding(dp(8),dp(10),dp(8),dp(10));row.addView(t);}
    private void chooseResult(){
        if(blocked())return;
        if(market==null)return;String[] m=market.clone();
        worker.execute(()->{
            ArrayList<File> files=new ArrayList<>();collect(new File(getFilesDir(),"UniversalTradingBotCache"),".json",files,4);
            ArrayList<File> valid=new ArrayList<>();ArrayList<String> labels=new ArrayList<>();
            files.sort((a,b)->Long.compare(b.lastModified(),a.lastModified()));
            for(File f:files){if(!f.getName().contains("backtest"))continue;try{JSONObject s=readResult(f.getAbsolutePath());if(matches(s,m)&&s.optJSONArray("trades_log")!=null){valid.add(f);labels.add(f.getName()+"\n"+s.optString("requested_start")+" ~ "+s.optString("requested_end"));}}catch(Exception ignored){}}
            runOnUiThread(()->{if(disposed||market==null||!Arrays.equals(m,market))return;if(valid.isEmpty()){status.setText("이 DB에 연결된 결과가 없습니다. 백테스트 실행 후 다시 선택하세요.");return;}
                new AlertDialog.Builder(this).setTitle("백테스트 실행 선택").setItems(labels.toArray(new String[0]),(d,i)->{resultPath=valid.get(i).getAbsolutePath();load();}).setNegativeButton("닫기",null).show();});
        });
    }

    private long intervalMillis(String tf){
        try{long n=Long.parseLong(tf.substring(0,tf.length()-1));char u=tf.charAt(tf.length()-1);return n*(u=='m'?60000L:u=='h'?3600000L:u=='d'?86400000L:0L);}catch(Exception e){return 0;}
    }
    private String num(JSONObject o,String key){return o.isNull(key)||!o.has(key)?"—":String.format(Locale.US,"%.6f",o.optDouble(key));}
    private String pass(JSONObject o,String key){return o.optBoolean(key)?"PASS":"FAIL";}
    private JSONObject selectedAudit(){
        JSONArray rows=auditPage.optJSONArray("rows");if(rows!=null)for(int i=0;i<rows.length();i++){JSONObject r=rows.optJSONObject(i);if(r!=null&&r.optLong("timestamp")==inspectedTime)return r;}return new JSONObject();
    }
    @Override public void inspect(long timestamp){
        inspectedTime=timestamp;JSONObject r=selectedAudit();
        if(r.length()==0){diagnostic.setText(auditPage.has("warmup")?"워밍업 / 계산 범위 밖 · "+auditPage.optInt("warmup")+"봉 준비 필요\n청산으로 계산이 종료된 이후에는 진단이 없습니다.":"전략 적용 후 봉을 터치하세요. 진단 패널을 눌러 상세 보기");return;}
        diagnostic.setText("거래량 "+num(r,"volume_ratio")+"× · RSI "+num(r,"rsi")+" · ADX "+num(r,"adx")
            +"\n거래량 "+pass(r,"volume_ok")+" / 1봉 "+pass(r,"one_bar_ok")+" / N봉 "+pass(r,"nbar_ok")+" / 쿨다운 "+pass(r,"cooldown_ok")
            +"\n"+decision(r)+" · "+r.optString("position")+" · 상세 진단 ▸");
        if(!r.optBoolean("volume_ready"))diagnostic.append("\n⚠ 4거래소 동일봉 거래량 부족");
        if(r.optBoolean("dual_touch"))diagnostic.append("\n⚠ TP/SL 동시 터치 · 청산 우선, 다음 SL");
    }
    private String decision(JSONObject r){
        if(r.optBoolean("liquidated"))return "계좌 청산 · 계산 종료";
        if(r.optBoolean("entry"))return "실제 진입 체결";
        if(!r.optString("pending","").isEmpty()&&!r.isNull("pending"))return "다음 봉 시가 진입 대기";
        for(String[] check:new String[][]{{"volume_ready","4거래소 데이터 부족"},{"volume_ok","거래량 미달"},{"one_bar_ok","1봉 변동 범위 밖"},{"nbar_ok","N봉 차단"},{"adx_ok","ADX 차단"},{"time_ok","시간 필터"},{"cooldown_ok","쿨다운/재진입 대기"}})if(!r.optBoolean(check[0]))return check[1];
        if(!r.optBoolean("can_enter"))return "포지션/진입한도/자금 제한";
        return "방향·RSI·연속봉·국면 조건 미충족";
    }
    private void showDiagnostic(){
        JSONObject r=selectedAudit(),p=auditPage.optJSONObject("parameters");
        if(r.length()==0||p==null){new AlertDialog.Builder(this).setTitle("전략 진단").setMessage(diagnostic.getText()).setPositiveButton("확인",null).show();return;}
        JSONObject ex=r.optJSONObject("exchanges");if(ex==null)ex=new JSONObject();
        String detail="선택 봉 UTC: "+new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",Locale.US){{setTimeZone(TimeZone.getTimeZone("UTC"));}}.format(new Date(inspectedTime))
            +"\n진입 판단: "+decision(r)+"\n신호: "+r.optString("signal","—")+" / 청산: "+r.optString("exit","—")
            +"\n4거래소 완전성: "+pass(r,"volume_ready")
            +"\n거래량: "+num(r,"volume_ratio")+" / "+num(p,"volume_break_multiplier")+"×"
            +"\nBinance: "+num(ex,"binance")+" · Bitget: "+num(ex,"bitget")
            +"\nOKX: "+num(ex,"okx")+" · Bybit: "+num(ex,"bybit")
            +"\n1봉 변동: "+num(r,"one_bar")+"% ["+num(p,"min_one_bar_vol")+" ~ "+num(p,"max_one_bar_vol")+"]"
            +"\nN봉 차단: "+num(r,"block_range")+" / "+num(p,"max_nbar_volatility")+"% · "+pass(r,"nbar_ok")
            +"\nRSI: "+num(r,"rsi")+" · LONG "+pass(r,"rsi_long_ok")+" / SHORT "+pass(r,"rsi_short_ok")
            +"\nADX: "+(p.optBoolean("use_adx_filter")?num(r,"adx")+" · "+pass(r,"adx_ok"):"OFF")
            +"\n시간: "+pass(r,"time_ok")+" · 쿨다운: "+pass(r,"cooldown_ok")
            +"\nLONG 연속봉: "+pass(r,"long_candle_ok")+" · SHORT 연속봉: "+pass(r,"short_candle_ok")
            +"\n현재 봉 TP/SL 산출: "+num(r,"tp_percent")+"% / "+num(r,"sl_percent")+"%"
            +"\n보유 포지션 고정 TP/SL: "+num(r,"tp")+" / "+num(r,"sl")
            +"\n포지션: "+r.optString("position_before")+" → "+r.optString("position")
            +"\n체결 모델: "+p.optString("backtest_execution_model")
            +"\n편도 비용: fee "+num(p,"backtest_fee_percent")+"% + slip "+num(p,"backtest_slippage_percent")+"%"
            +"\n기간: 선택 DB 전체 · 워밍업 "+auditPage.optInt("warmup")+"봉"
            +"\nTP/SL 동시 터치: "+(r.optBoolean("dual_touch")?"경고 · 청산 우선, 다음 SL":"없음")
            +"\n※ DB 백테스트 결과이며 실거래 주문 기록은 아닙니다.";
        TextView text=new TextView(this);text.setText(detail);text.setTextIsSelectable(true);text.setPadding(dp(16),dp(12),dp(16),dp(12));
        ScrollView scroll=new ScrollView(this);scroll.addView(text);
        new AlertDialog.Builder(this).setTitle("전략 진단 · 실제 엔진").setView(scroll).setNegativeButton("닫기",null).show();
    }
    private void strategyDialog(){
        if(blocked()||market==null)return;
        if(!market[1].equals("bitget")){status.setText("전략 적용은 BITGET 시장을 선택하세요.");return;}
        new AlertDialog.Builder(this).setTitle("선택 DB에 적용할 전략")
            .setItems(new String[]{"현재 선택한 전략 적용","JSON 붙여넣기","JSON 파일 불러오기","제공한 Pine v19 수치"},(d,i)->{
                if(i==0){if(strategyParameters.isEmpty())status.setText("먼저 JSON 전략을 불러오세요.");else confirmStrategy(strategyParameters);}
                else if(i==1){EditText input=new EditText(this);input.setMinLines(5);input.setHint("전략 JSON");new AlertDialog.Builder(this).setTitle("JSON 붙여넣기").setView(input).setPositiveButton("읽기",(a,b)->parseStrategy(input.getText().toString())).setNegativeButton("취소",null).show();}
                else if(i==2)startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),IMPORT_JSON);
                else worker.execute(()->{try{String json=python().getModule("universal_bot.chart_workspace").callAttr("preset").toString();runOnUiThread(()->parseStrategy(json));}catch(Exception e){error(e);}});
            }).setNegativeButton("닫기",null).show();
    }
    private void parseStrategy(String json){
        if(blocked())return;busy=true;
        worker.execute(()->{try{
            JSONObject parsed=new JSONObject(python().getModule("mobile_bridge").callAttr("parse_pasted_backtest_json",json).toString());
            JSONArray items=parsed.getJSONArray("items");String[] names=new String[items.length()];
            for(int i=0;i<names.length;i++)names[i]="전략 "+(i+1)+" · "+items.getJSONObject(i).optString("label","JSON");
            runOnUiThread(()->{busy=false;if(disposed)return;
                if(market==null)return;
                if((!parsed.optString("symbol").isEmpty()&&!parsed.optString("symbol").equals(market[2]))||(!parsed.optString("timeframe").isEmpty()&&!parsed.optString("timeframe").equals(market[3]))){status.setText("⚠ JSON 심볼·주기가 선택한 DB 시장과 다릅니다.");return;}
                new AlertDialog.Builder(this).setTitle("전략 선택").setItems(names,(d,i)->confirmStrategy(items.optJSONObject(i).optJSONObject("effective_parameters").toString())).setNegativeButton("취소",null).show();
            });
        }catch(Exception e){busy=false;error(e);}});
    }
    private void confirmStrategy(String parameters){
        if(blocked()||market==null)return;
        try{
            JSONObject p=new JSONObject(parameters);
            new AlertDialog.Builder(this).setTitle("DB 전체 기간에 전략 적용")
                .setMessage(new File(selectedDatabasePath).getName()+"\n"+market[2]+" · "+market[3]+"\n체결: "+p.optString("backtest_execution_model","signal_close")+"\n기존 DB 전체 기간으로 새 결과를 저장합니다. 워밍업 봉은 진입에서 제외합니다.")
                .setPositiveButton("적용",(d,i)->applyStrategy(parameters)).setNegativeButton("취소",null).show();
        }catch(Exception e){error(e);}
    }
    private void applyStrategy(String parameters){
        if(blocked()||market==null)return;
        busy=true;selector.setEnabled(false);databaseSelector.setEnabled(false);generation.incrementAndGet();
        String[] m=market.clone();strategyParameters=parameters;cancelFile=new File(getCacheDir(),"chart-cancel-"+UUID.randomUUID());
        final File cancellation=cancelFile;
        ProgressDialog progress=new ProgressDialog(this);progress.setTitle("전략 계산");progress.setMessage("선택 DB 전체 기간을 검증하고 봉별 진단을 저장합니다.");progress.setCancelable(false);
        progress.setButton(DialogInterface.BUTTON_NEGATIVE,"중지",(d,i)->{try{cancellation.createNewFile();}catch(IOException ignored){}});
        progress.show();
        worker.execute(()->{try{
            String result=python().getModule("universal_bot.chart_workspace").callAttr("apply_strategy",m[0],m[2],m[3],parameters,cancellation.getAbsolutePath()).toString();
            String saved=new JSONObject(result).getString("result_path");
            runOnUiThread(()->{busy=false;progress.dismiss();if(disposed)return;selector.setEnabled(true);databaseSelector.setEnabled(true);resultPath=saved;getSharedPreferences("universal_bot",MODE_PRIVATE).edit().putString("chart_result:"+m[0],saved).putString("chart_parameters:"+m[0],parameters).apply();loadedResultPath=null;load();});
        }catch(Exception e){runOnUiThread(()->{busy=false;progress.dismiss();if(disposed)return;selector.setEnabled(true);databaseSelector.setEnabled(true);warning.setText("⚠ 전략 적용 실패: "+e.getMessage());});}
        finally{cancellation.delete();}});
    }
    private void error(Exception e){runOnUiThread(()->{if(!disposed)status.setText("오류: "+e.getMessage());});}
    private void manageDatabase(){
        if(blocked())return;
        new AlertDialog.Builder(this).setTitle("DB 관리")
            .setItems(new String[]{"DB 선택","DB 파일 불러오기 · 앱에 저장","선택 DB 외부에 저장","선택 DB 삭제","마지막 삭제 복구","휴지통 비우기"},(d,i)->{
                if(i==0)showDatabasePicker();
                if(i==1)startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),IMPORT_DB);
                if(i==2&&market!=null){exportPath=selectedDatabasePath;startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/octet-stream").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,new File(exportPath).getName()),EXPORT_DB);}
                if(i==3&&market!=null)deleteDatabase();
                if(i==4)restoreDatabase();
                if(i==5)emptyTrash();
            }).setNegativeButton("닫기",null).show();
    }
    private void deleteDatabase(){
        final File source=new File(selectedDatabasePath);
        new AlertDialog.Builder(this).setTitle("DB 삭제").setMessage(source.getName()+"\n앱 DB 목록에서 제거합니다. 마지막 삭제는 복구할 수 있습니다.").setNegativeButton("취소",null).setPositiveButton("삭제",(d,i)->{
            if(blocked())return;
            try{
                if(!source.getCanonicalPath().startsWith(new File(getFilesDir(),"UniversalTradingBotCache").getCanonicalPath()+File.separator))throw new IOException("앱에서 저장한 DB만 삭제할 수 있습니다.");
                File trash=new File(source.getAbsolutePath()+"."+System.currentTimeMillis()+".deleted");
                if(!source.renameTo(trash))throw new IOException("DB 삭제에 실패했습니다.");
                for(String suffix:new String[]{"-wal","-shm"}){
                    File sidecar=new File(source.getAbsolutePath()+suffix);
                    if(sidecar.exists()&&!sidecar.renameTo(new File(trash.getAbsolutePath()+suffix))){
                        trash.renameTo(source);
                        for(String prior:new String[]{"-wal","-shm"})new File(trash.getAbsolutePath()+prior).renameTo(new File(source.getAbsolutePath()+prior));
                        throw new IOException("DB 보조 파일 이동 실패 · 삭제 취소");
                    }
                }
                getSharedPreferences("universal_bot",MODE_PRIVATE).edit().putString("deleted_db",trash.getAbsolutePath()).putString("deleted_db_original",source.getAbsolutePath()).remove("chart_db_path").apply();
                resultPath="";loadedResultPath=null;selectedDatabasePath="";auditPage=new JSONObject();trades=new JSONArray();scanDatabases();
            }catch(Exception e){error(e);}
        }).show();
    }
    private void emptyTrash(){
        new AlertDialog.Builder(this).setTitle("휴지통 영구 삭제").setMessage("삭제한 DB를 영구 제거하고 저장 공간을 확보합니다. 복구할 수 없습니다.").setNegativeButton("취소",null).setPositiveButton("비우기",(d,i)->{
            if(blocked())return;
            ArrayList<File> files=new ArrayList<>();collect(new File(getFilesDir(),"UniversalTradingBotCache"),".deleted",files,4);
            int failed=0;for(File f:files){if(!f.delete())failed++;for(String suffix:new String[]{"-wal","-shm"})new File(f.getAbsolutePath()+suffix).delete();}
            status.setText(failed==0?"휴지통을 비웠습니다.":failed+"개 DB를 삭제하지 못했습니다.");
        }).show();
    }
    private void restoreDatabase(){
        if(blocked())return;
        android.content.SharedPreferences p=getSharedPreferences("universal_bot",MODE_PRIVATE);
        File trash=new File(p.getString("deleted_db","")),original=new File(p.getString("deleted_db_original",""));
        if(!trash.isFile()||original.exists()||!trash.renameTo(original)){status.setText("복구할 DB가 없거나 같은 이름의 파일이 있습니다.");return;}
        for(String suffix:new String[]{"-wal","-shm"})new File(trash.getAbsolutePath()+suffix).renameTo(new File(original.getAbsolutePath()+suffix));
        selectedDatabasePath=original.getAbsolutePath();p.edit().remove("deleted_db").remove("deleted_db_original").apply();scanDatabases();
    }
    @Override protected void onActivityResult(int request,int result,Intent intent){
        super.onActivityResult(request,result,intent);
        if(result!=RESULT_OK||intent==null||intent.getData()==null||blocked())return;
        Uri uri=intent.getData();String source=exportPath;busy=true;
        worker.execute(()->{
            File temporary=null;
            try{
                if(request==EXPORT_DB){
                    temporary=new File(getCacheDir(),"db-export-"+UUID.randomUUID()+".db");
                    python().getModule("universal_bot.chart_workspace").callAttr("export_snapshot",source,temporary.getAbsolutePath());
                    try(InputStream in=new FileInputStream(temporary);OutputStream out=getContentResolver().openOutputStream(uri,"w")){if(out==null)throw new IOException("저장 위치를 열 수 없습니다.");copy(in,out,Long.MAX_VALUE);}
                }else if(request==IMPORT_DB){
                    File dir=new File(getFilesDir(),"UniversalTradingBotCache");dir.mkdirs();
                    temporary=new File(dir,"import-"+UUID.randomUUID()+".importing");
                    try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(temporary)){if(in==null)throw new IOException("파일을 열 수 없습니다.");copy(in,out,Math.max(0,dir.getUsableSpace()-64L*1024*1024));}
                    try(SQLiteDatabase db=SQLiteDatabase.openDatabase(temporary.getAbsolutePath(),null,SQLiteDatabase.OPEN_READONLY);
                        Cursor c=db.rawQuery("SELECT timestamp,exchange,symbol,timeframe,open,high,low,close,volume FROM ohlcv WHERE asset_class='crypto' LIMIT 1",null)){
                        if(!c.moveToFirst())throw new IOException("지원하는 OHLCV DB가 아니거나 비어 있습니다.");
                    }
                    String display="database";
                    try(Cursor c=getContentResolver().query(uri,new String[]{android.provider.OpenableColumns.DISPLAY_NAME},null,null,null)){
                        if(c!=null&&c.moveToFirst())display=c.getString(0);
                    }
                    display=display.replaceAll("[^a-zA-Z0-9가-힣._-]","_").replaceAll("(?i)\\.db$","");
                    if(display.length()>80)display=display.substring(0,80);
                    File saved=new File(dir,display+"-"+UUID.randomUUID().toString().substring(0,8)+".db");
                    if(!temporary.renameTo(saved))throw new IOException("DB 저장 실패");temporary=null;selectedDatabasePath=saved.getAbsolutePath();
                }else if(request==IMPORT_JSON){
                    ByteArrayOutputStream bytes=new ByteArrayOutputStream();
                    try(InputStream in=getContentResolver().openInputStream(uri)){if(in==null)throw new IOException("JSON 파일 읽기 실패");copy(in,bytes,8L*1024*1024);}
                    String json=bytes.toString("UTF-8");runOnUiThread(()->{busy=false;if(!disposed)parseStrategy(json);});return;
                }
                runOnUiThread(()->{busy=false;if(disposed)return;status.setText("DB 저장 완료");if(request==IMPORT_DB)scanDatabases();});
            }catch(Exception e){busy=false;error(e);}
            finally{if(temporary!=null)temporary.delete();}
        });
    }
    private void copy(InputStream in,OutputStream out,long limit)throws IOException{
        byte[] buffer=new byte[65536];long total=0;int n;while((n=in.read(buffer))!=-1){total+=n;if(total>limit)throw new IOException("파일이 너무 크거나 저장 공간이 부족합니다.");out.write(buffer,0,n);}
    }

    @Override protected void onDestroy(){disposed=true;if(cancelFile!=null)try{cancelFile.createNewFile();}catch(IOException ignored){}generation.incrementAndGet();worker.shutdownNow();super.onDestroy();}
}
