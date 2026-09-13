package com.nictunz.universalbacktester;

import android.app.*;
import android.content.Intent;
import android.content.DialogInterface;
import android.net.Uri;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.graphics.Bitmap;
import android.graphics.Canvas;
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
    private FrameLayout chartFrame;
    private StrategyDiagnosticPanel strategyPanel;
    private TextView status;
    private Spinner selector;
    private Button databaseSelector;
    private String[] market;
    private String selectedDatabasePath="";
    private int total,offset,width=160;
    private JSONArray trades=new JSONArray();
    private String resultPath="";
    private volatile boolean disposed;
    private String loadedResultPath;
    private long loadedResultModified;
    private JSONObject loadedResult = new JSONObject();
    private float zoomWidth=160;
    private TextView diagnostic, warning;
    private JSONObject dataQuality=new JSONObject();
    private JSONObject auditPage = new JSONObject();
    private String strategyParameters = "";
    private volatile boolean busy;
    private String exportPath = "";
    private File cancelFile;
    private long inspectedTime;
    private static final int IMPORT_DB=8201, EXPORT_DB=8202, IMPORT_JSON=8203, EXPORT_TEXT=8204, EXPORT_IMAGE=8205;
    private String exportText="";
    private Bitmap exportBitmap;
    private JSONObject activeSummary=new JSONObject();
    private JSONArray annotations=new JSONArray(), bookmarks=new JSONArray();
    private TextView modeText;
    private LinearLayout replayBar;
    private boolean fullscreen, playing, loading;
    private int replayLimit;
    private long pendingInspect;
    private boolean ema=true, bands;
    private int indicatorPane=1;
    private final Handler playback=new Handler(Looper.getMainLooper());
    private final Runnable playbackTick=new Runnable(){public void run(){
        if(disposed||!playing)return;
        if(!loading&&!busy){if(replayLimit>=total){pauseReplay();return;}stepReplay(1);}
        playback.postDelayed(this,750);
    }};
    private android.content.SharedPreferences prefs(){return getSharedPreferences("universal_bot",MODE_PRIVATE);}
    private String workspaceKey(){return market==null?"":"workspace:"+market[0]+":"+market[1]+":"+market[2]+":"+market[3];}
    private int availableBars(){return replayLimit>0?Math.min(total,replayLimit):total;}
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
        databaseSelector=new Button(this);databaseSelector.setAllCaps(false);databaseSelector.setText("DB 선택");databaseSelector.setOnClickListener(v->manageDatabase());bar.addView(databaseSelector,new LinearLayout.LayoutParams(dp(132),dp(48)));
        selector=new Spinner(this);bar.addView(selector,new LinearLayout.LayoutParams(0,dp(48),1));
        selector.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> p){}
            public void onItemSelected(AdapterView<?> p,View v,int pos,long id){
                if(pos<0||pos>=markets.size())return;
                if(busy)return;
                saveWorkspace();pauseReplay();
                market=markets.get(pos);total=Integer.parseInt(market[4]);offset=Math.max(0,total-width);trades=new JSONArray();restoreWorkspace();load();
            }
        });
        root.addView(bar);
        modeText=new TextView(this);modeText.setTextColor(Color.CYAN);modeText.setTextSize(12);modeText.setPadding(dp(10),dp(4),dp(10),dp(4));modeText.setText("DB 분석 · 실시간 시세 아님");root.addView(modeText);
        HorizontalScrollView toolScroll=new HorizontalScrollView(this);toolScroll.setHorizontalScrollBarEnabled(false);
        LinearLayout tools=new LinearLayout(this);
        toolButton(tools,"차트 설정",this::chartSettings);
        toolButton(tools,"진단표",()->{strategyPanel.setVisibility(strategyPanel.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE);strategyPanel.resize();});
        toolButton(tools,"데이터 검사",this::showDataQuality);
        toolButton(tools,"전략",this::strategyDialog);
        toolButton(tools,"성과",this::showPerformance);
        toolButton(tools,"거래",this::showTrades);
        toolButton(tools,"리플레이",this::replayMenu);
        toolButton(tools,"그리기·저장",this::chartTools);
        toolButton(tools,"LIVE 서버",()->{pauseReplay();startActivity(new Intent(this,ServerDashboardActivity.class));});
        toolScroll.addView(tools);root.addView(toolScroll);
        status=new TextView(this);status.setTextColor(Color.LTGRAY);status.setTextSize(12);status.setMaxLines(2);status.setPadding(dp(10),0,dp(10),0);status.setText("저장된 코인 DB 검색 중…");root.addView(status);
        warning=new TextView(this);warning.setTextColor(Color.rgb(255,190,75));warning.setTextSize(12);warning.setMaxLines(2);warning.setPadding(dp(10),dp(4),dp(10),dp(4));root.addView(warning);
        warning.setOnClickListener(v->showDataQuality());
        diagnostic=new TextView(this);diagnostic.setTextColor(Color.LTGRAY);diagnostic.setTextSize(12);diagnostic.setMaxLines(2);diagnostic.setPadding(dp(10),dp(4),dp(10),dp(4));diagnostic.setText("전략 적용 후 봉을 터치하면 실제 엔진 진단이 표시됩니다.");diagnostic.setOnClickListener(v->showDiagnostic());root.addView(diagnostic);
        chartFrame=new FrameLayout(this);chart=new CandleChartView(this,this);chartFrame.addView(chart,new FrameLayout.LayoutParams(-1,-1));
        strategyPanel=new StrategyDiagnosticPanel(this);chartFrame.addView(strategyPanel);chartFrame.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->{if(r-l!=or-ol||b-t!=ob-ot)strategyPanel.resize();});
        root.addView(chartFrame,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout actions=new LinearLayout(this);
        addButton(actions,"날짜",()->{Calendar now=Calendar.getInstance();new DatePickerDialog(this,(v,y,m,d)->jumpDate(y,m,d),now.get(Calendar.YEAR),now.get(Calendar.MONTH),now.get(Calendar.DAY_OF_MONTH)).show();});
        addButton(actions,"‹ 거래",()->navigateTrade(-1));
        addButton(actions,"거래 ›",()->navigateTrade(1));
        addButton(actions,"최근",()->{offset=Math.max(0,availableBars()-width);load();});
        root.addView(actions);
        replayBar=new LinearLayout(this);
        addButton(replayBar,"−1봉",()->{pauseReplay();stepReplay(-1);});
        addButton(replayBar,"재생/정지",()->{if(playing)pauseReplay();else if(replayLimit>0){playing=true;playback.post(playbackTick);}});
        addButton(replayBar,"+1봉",()->{pauseReplay();stepReplay(1);});
        addButton(replayBar,"종료",()->{pauseReplay();replayLimit=0;replayBar.setVisibility(View.GONE);load();});
        replayBar.setVisibility(View.GONE);root.addView(replayBar);setContentView(root);
        scanDatabases();
    }
    private void scanDatabases(){
        loading=false;generation.incrementAndGet();
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
        saveWorkspace();pauseReplay();
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
        loading=true;
        dataQuality=new JSONObject();
        strategyPanel.setRows(Collections.singletonList(new String[]{"상태","차트 불러오는 중…",String.valueOf(StrategyDiagnosticPanel.NEUTRAL)}));
        int request=generation.incrementAndGet();String[] m=market.clone();
        int start=offset,count=Math.min(width,Math.max(0,availableBars()-offset));String file=resultPath;boolean replay=replayLimit>0;
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
                JSONArray indicators=new JSONArray();String indicatorWarning="";
                if(!rows.isEmpty())try{indicators=new JSONArray(python().getModule("universal_bot.chart_indicators").callAttr("indicator_page",m[0],m[1],m[2],m[3],(long)rows.get(0)[0],(long)rows.get(rows.size()-1)[0]).toString());}
                catch(Exception e){indicatorWarning=" · 보조지표 오류: "+e.getMessage();}
                final JSONArray displayedIndicators=indicators;
                JSONObject page=new JSONObject();String alert="";
                if(!m[1].equals("bitget"))alert="⚠ 전략 OHLC 기준은 BITGET입니다. 현재 "+m[1]+" 캔들입니다.";
                else if(match && s.has("chart_audit_database") && !rows.isEmpty()){
                    try{page=new JSONObject(python().getModule("universal_bot.chart_workspace").callAttr("audit_page",file,(long)rows.get(0)[0],(long)rows.get(rows.size()-1)[0]).toString());}
                    catch(Exception e){match=false;alert="⚠ "+e.getMessage();}
                }else alert=match?"⚠ 이전 결과는 봉별 진단이 없습니다. 전략을 다시 적용하세요.":"⚠ 전략 미적용 · 캔들 데이터만 표시합니다.";
                JSONObject quality=new JSONObject();
                if(!rows.isEmpty())try{
                    quality=new JSONObject(python().getModule("universal_bot.chart_quality").callAttr("quality_page",m[0],m[1],m[2],m[3],(long)rows.get(0)[0],(long)rows.get(rows.size()-1)[0],intervalMillis(m[3])).toString());
                    int affected=quality.optJSONArray("rows").length();
                    alert="데이터 검사 · "+quality.optInt("bars")+"봉 · 주의 "+affected+"봉 · 눌러 상세 보기\n"+alert;
                }catch(Exception e){alert="⚠ 데이터 검사 실패: "+e.getMessage()+"\n"+alert;}
                final JSONObject shownQuality=quality;
                final JSONObject shownPage=page;final String shownAlert=alert+indicatorWarning;
                final JSONObject shownSummary=match&&!replay?s:new JSONObject();
                JSONArray log=match?s.optJSONArray("trades_log"):null;
                JSONArray visibleTrades=new JSONArray();
                long cutoff=rows.isEmpty()?0:(long)rows.get(rows.size()-1)[0];
                if(log!=null)for(int i=0;i<log.length();i++){JSONObject trade=log.optJSONObject(i);if(trade!=null&&(!replay||CandleChartView.millis(trade.optString("exit_time"))<=cutoff))visibleTrades.put(trade);}
                final JSONArray data=visibleTrades;
                String msg=match?String.format(Locale.US,"수익 %.2f%% · MDD %.2f%% · %d거래",s.optDouble("return_percent"),s.optDouble("max_drawdown_percent"),data.length()):"캔들 보기 · ‘결과’에서 이 DB의 백테스트를 선택하세요";
                if(replay)msg="리플레이 · "+data.length()+"건 청산 확인 · 전체 성과 숨김";
                if(data.length()>0&&!data.optJSONObject(0).has("tp_price"))msg+=" · TP/SL 선은 재실행 후 표시";
                final String message=msg;
                runOnUiThread(()->{if(disposed||request!=generation.get())return;loading=false;trades=data;activeSummary=shownSummary;auditPage=shownPage;dataQuality=shownQuality;warning.setText(shownAlert);chart.setData(rows,data);chart.setQuality(shownQuality.optJSONArray("rows"));chart.setAudit(shownPage.optJSONArray("rows"));chart.setOverlays(displayedIndicators);chart.setDrawings(visibleAnnotations(cutoff));chart.options(ema,bands,indicatorPane);if(!rows.isEmpty()){long focus=pendingInspect>0?pendingInspect:(long)rows.get(rows.size()-1)[0];chart.focusTime(focus);pendingInspect=0;}modeText.setText((replay?"REPLAY · 미래 봉/청산 숨김":"DB 분석 · 실시간 시세 아님")+" · "+m[2]+" "+m[3]);status.setText(message);saveWorkspace();});
            }catch(Exception e){runOnUiThread(()->{if(!disposed&&request==generation.get()){loading=false;trades=new JSONArray();activeSummary=new JSONObject();auditPage=new JSONObject();chart.setData(Collections.emptyList(),trades);chart.setAudit(null);chart.setOverlays(null);status.setText("차트 읽기 실패: "+e.getMessage());}});}
        });
    }
    @Override public void move(int bars){offset=Math.max(0,Math.min(Math.max(0,availableBars()-width),offset+bars));load();}
    @Override public void zoom(float factor){zoomWidth=Math.max(30,Math.min(600,zoomWidth/factor));int next=(int)zoomWidth;if(next==width)return;int center=offset+width/2;width=next;offset=Math.max(0,Math.min(Math.max(0,availableBars()-width),center-width/2));load();}
    private void jumpDate(int y,int month,int day){Calendar c=Calendar.getInstance(TimeZone.getTimeZone("UTC"));c.clear();c.set(y,month,day);jump(c.getTimeInMillis());}
    private void jump(long ms){
        if(market==null)return;String[] m=market.clone();int request=generation.incrementAndGet();
        worker.execute(()->{try(SQLiteDatabase db=SQLiteDatabase.openDatabase(m[0],null,SQLiteDatabase.OPEN_READONLY);Cursor c=db.rawQuery("SELECT count(*) FROM ohlcv WHERE asset_class='crypto' AND exchange=? AND symbol=? AND timeframe=? AND timestamp<?",new String[]{m[1],m[2],m[3],""+ms})){
            c.moveToFirst();int n=c.getInt(0);runOnUiThread(()->{if(disposed||request!=generation.get())return;offset=Math.max(0,Math.min(Math.max(0,availableBars()-width),n-width/3));pendingInspect=ms;load();});
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
        updateStrategyPanel(r);
        if(r.length()==0){diagnostic.setText(auditPage.has("warmup")?"워밍업 / 계산 범위 밖 · "+auditPage.optInt("warmup")+"봉 준비 필요\n청산으로 계산이 종료된 이후에는 진단이 없습니다.":"전략 적용 후 봉을 터치하세요. 진단 패널을 눌러 상세 보기");return;}
        diagnostic.setText("거래량 "+num(r,"volume_ratio")+"× · RSI "+num(r,"rsi")+" · ADX "+num(r,"adx")
            +"\n거래량 "+pass(r,"volume_ok")+" / 1봉 "+pass(r,"one_bar_ok")+" / N봉 "+pass(r,"nbar_ok")+" / 쿨다운 "+pass(r,"cooldown_ok")
            +"\n"+decision(r)+" · "+r.optString("position")+" · 상세 진단 ▸");
        if(!r.optBoolean("volume_ready"))diagnostic.append("\n⚠ 4거래소 동일봉 거래량 부족");
        if(r.optBoolean("dual_touch"))diagnostic.append("\n⚠ TP/SL 동시 터치 · 청산 우선, 다음 SL");
    }
    private void updateStrategyPanel(JSONObject r){
        int good=StrategyDiagnosticPanel.PASS,bad=StrategyDiagnosticPanel.FAIL,plain=StrategyDiagnosticPanel.NEUTRAL,info=StrategyDiagnosticPanel.INFO,yellow=StrategyDiagnosticPanel.FIXED;
        ArrayList<String[]> rows=new ArrayList<>();
        java.text.SimpleDateFormat fmt=new java.text.SimpleDateFormat("MM-dd HH:mm",Locale.US);fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        panelRow(rows,"선택 봉 UTC",fmt.format(new Date(inspectedTime)),info);
        boolean parity=market!=null&&market[1].equals("bitget")&&market[2].equals("BTC/USDT:USDT")&&market[3].equals("15m");
        panelRow(rows,"v19 기준 차트",parity?"BITGET BTC · 15분":"다른 시장/주기",parity?good:yellow);
        if(r.length()==0){panelRow(rows,"진단",auditPage.has("warmup")?"워밍업 / 계산 범위 밖":"전략 적용 필요",yellow);panelRow(rows,"조작","제목 터치: 접기\n길게 누르기: 위치",plain);strategyPanel.setRows(rows);return;}
        JSONObject p=auditPage.optJSONObject("parameters");if(p==null)p=new JSONObject();JSONObject ex=r.optJSONObject("exchanges");if(ex==null)ex=new JSONObject();
        panelRow(rows,"4거래소 완전성",pass(r,"volume_ready"),r.optBoolean("volume_ready")?good:bad);
        panelRow(rows,"거래량","×"+panelNumber(r,"volume_ratio")+" / ×"+panelNumber(p,"volume_break_multiplier"),r.optBoolean("volume_ok")?good:bad);
        panelRow(rows,"Bin / Bitget",panelNumber(ex,"binance")+" / "+panelNumber(ex,"bitget"),plain);
        panelRow(rows,"OKX / Bybit",panelNumber(ex,"okx")+" / "+panelNumber(ex,"bybit"),plain);
        panelRow(rows,"1봉 변동",panelNumber(r,"one_bar")+"%",r.optBoolean("one_bar_ok")?good:bad);
        panelRow(rows,"N봉 차단",p.optBoolean("use_nbar_volatility_block")?panelNumber(r,"block_range")+"% / "+panelNumber(p,"max_nbar_volatility")+"%":"OFF",r.optBoolean("nbar_ok")?good:bad);
        panelRow(rows,"RSI",p.optBoolean("use_rsi_filter")?panelNumber(r,"rsi"):"OFF",!p.optBoolean("use_rsi_filter")?plain:r.optBoolean("rsi_long_ok")||r.optBoolean("rsi_short_ok")?good:bad);
        panelRow(rows,"ADX",p.optBoolean("use_adx_filter")?panelNumber(r,"adx"):"OFF",!p.optBoolean("use_adx_filter")?plain:r.optBoolean("adx_ok")?good:bad);
        panelRow(rows,"봉 TP / SL",panelNumber(r,"tp_percent")+"% / "+panelNumber(r,"sl_percent")+"%",yellow);
        panelRow(rows,"고정 TP / SL",panelNumber(r,"tp")+" / "+panelNumber(r,"sl"),yellow);
        panelRow(rows,"쿨다운",pass(r,"cooldown_ok"),r.optBoolean("cooldown_ok")?good:bad);
        panelRow(rows,"포지션",r.optString("position","—"),plain);
        panelRow(rows,"진입 판정",decision(r),r.optBoolean("entry")?good:bad);
        int closed=0,wins=0;double pnl=0;
        for(int i=0;i<trades.length();i++){JSONObject trade=trades.optJSONObject(i);if(trade==null)continue;long exit=CandleChartView.millis(trade.optString("exit_time"));if(exit<0||exit>inspectedTime)continue;closed++;double profit=trade.optDouble("pnl",0);pnl+=profit;if(profit>0)wins++;}
        panelRow(rows,"봉까지 거래/승률",closed+" / "+String.format(Locale.US,"%.1f%%",closed==0?0:100.0*wins/closed),plain);
        panelRow(rows,"봉까지 실현손익",String.format(Locale.US,"%+.2f",pnl),pnl>=0?good:bad);
        panelRow(rows,"편도 비용",panelNumber(p,"backtest_fee_percent")+"% fee + "+panelNumber(p,"backtest_slippage_percent")+"% slip",yellow);
        if(r.optBoolean("dual_touch"))panelRow(rows,"동시 터치","청산 우선 · 이후 SL",bad);
        strategyPanel.setRows(rows);
    }
    private void panelRow(List<String[]> rows,String key,String value,int color){rows.add(new String[]{key,value,String.valueOf(color)});}
    private String panelNumber(JSONObject row,String key){double n=row.optDouble(key,Double.NaN);return Double.isFinite(n)?String.format(Locale.US,"%.4f",n).replaceAll("0+$", "").replaceAll("\\.$", ""):"—";}
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
            .setItems(new String[]{"현재 선택한 전략 적용","JSON 붙여넣기","JSON 파일 불러오기","제공한 Pine v19 수치","수치 직접 편집"},(d,i)->{
                if(i==0){if(strategyParameters.isEmpty())status.setText("먼저 JSON 전략을 불러오세요.");else confirmStrategy(strategyParameters);}
                else if(i==1){EditText input=new EditText(this);input.setMinLines(5);input.setHint("전략 JSON");new AlertDialog.Builder(this).setTitle("JSON 붙여넣기").setView(input).setPositiveButton("읽기",(a,b)->parseStrategy(input.getText().toString())).setNegativeButton("취소",null).show();}
                else if(i==2)startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),IMPORT_JSON);
                else if(i==4)editStrategy();
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
        pauseReplay();busy=true;selector.setEnabled(false);databaseSelector.setEnabled(false);generation.incrementAndGet();
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
            .setItems(new String[]{"DB 선택","DB 파일 불러오기 · 앱에 저장","선택 DB 외부에 저장","선택 DB 삭제","마지막 삭제 복구","휴지통 비우기","DB 다운로드 화면"},(d,i)->{
                if(i==0)showDatabasePicker();
                if(i==1)startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),IMPORT_DB);
                if(i==2&&market!=null){exportPath=selectedDatabasePath;startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/octet-stream").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,new File(exportPath).getName()),EXPORT_DB);}
                if(i==3&&market!=null)deleteDatabase();
                if(i==4)restoreDatabase();
                if(i==5)emptyTrash();
                if(i==6)startActivity(new Intent(this,MainActivity.class));
            }).setNegativeButton("닫기",null).show();
    }
    private void deleteDatabase(){
        final File source=new File(selectedDatabasePath);
        new AlertDialog.Builder(this).setTitle("DB 삭제").setMessage(source.getName()+"\n앱 DB 목록에서 제거합니다. 마지막 삭제는 복구할 수 있습니다.").setNegativeButton("취소",null).setPositiveButton("삭제",(d,i)->{
            if(blocked())return;
            busy=true;generation.incrementAndGet();
            worker.execute(()->{
            try{
                if(BacktestForegroundService.isWorkerRunning())throw new IOException("백테스트가 실행 중입니다. 삭제를 취소했습니다.");
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
                runOnUiThread(()->{busy=false;if(disposed)return;resultPath="";loadedResultPath=null;selectedDatabasePath="";auditPage=new JSONObject();trades=new JSONArray();scanDatabases();});
            }catch(Exception e){busy=false;error(e);}
            });
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
        if(result!=RESULT_OK||intent==null||intent.getData()==null){
            if(request==EXPORT_IMAGE&&exportBitmap!=null){exportBitmap.recycle();exportBitmap=null;}return;
        }
        if(blocked())return;
        Uri uri=intent.getData();String source=exportPath;String textToExport=exportText;Bitmap imageToExport=exportBitmap;busy=true;
        worker.execute(()->{
            File temporary=null;
            try{
                if(request==EXPORT_TEXT){
                    try(OutputStream out=getContentResolver().openOutputStream(uri,"w")){if(out==null)throw new IOException("저장 위치를 열 수 없습니다.");out.write(textToExport.getBytes("UTF-8"));}
                }else if(request==EXPORT_IMAGE){
                    try(OutputStream out=getContentResolver().openOutputStream(uri,"w")){if(out==null||imageToExport==null||!imageToExport.compress(Bitmap.CompressFormat.PNG,100,out))throw new IOException("차트 이미지 저장 실패");}
                }else if(request==EXPORT_DB){
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
                runOnUiThread(()->{busy=false;if(disposed)return;status.setText("파일 저장 완료");if(request==IMPORT_DB)scanDatabases();});
            }catch(Exception e){busy=false;error(e);}
            finally{if(temporary!=null)temporary.delete();if(request==EXPORT_IMAGE&&imageToExport!=null){imageToExport.recycle();exportBitmap=null;}}
        });
    }
    private void copy(InputStream in,OutputStream out,long limit)throws IOException{
        byte[] buffer=new byte[65536];long total=0;int n;while((n=in.read(buffer))!=-1){total+=n;if(total>limit)throw new IOException("파일이 너무 크거나 저장 공간이 부족합니다.");out.write(buffer,0,n);}
    }


    private void toolButton(LinearLayout row,String title,Runnable action){
        Button b=new Button(this);b.setText(title);b.setAllCaps(false);b.setTextSize(12);b.setOnClickListener(v->action.run());
        row.addView(b,new LinearLayout.LayoutParams(dp(100),dp(46)));
    }
    private void saveWorkspace(){
        if(market==null)return;
        try{
            JSONObject value=new JSONObject().put("offset",offset).put("width",width).put("replay",replayLimit)
                .put("ema",ema).put("bands",bands).put("pane",indicatorPane)
                .put("drawings",annotations).put("bookmarks",bookmarks);
            prefs().edit().putString(workspaceKey(),value.toString()).apply();
        }catch(JSONException ignored){}
    }
    private void restoreWorkspace(){
        try{
            JSONObject value=new JSONObject(prefs().getString(workspaceKey(),"{}"));
            width=Math.max(30,Math.min(600,value.optInt("width",160)));zoomWidth=width;
            replayLimit=Math.max(0,Math.min(total,value.optInt("replay",0)));
            offset=Math.max(0,Math.min(Math.max(0,availableBars()-width),value.optInt("offset",Math.max(0,total-width))));
            ema=value.optBoolean("ema",true);bands=value.optBoolean("bands",false);indicatorPane=Math.max(0,Math.min(3,value.optInt("pane",1)));
            annotations=value.optJSONArray("drawings");if(annotations==null)annotations=new JSONArray();
            bookmarks=value.optJSONArray("bookmarks");if(bookmarks==null)bookmarks=new JSONArray();
        }catch(JSONException e){replayLimit=0;annotations=new JSONArray();bookmarks=new JSONArray();}
        replayBar.setVisibility(replayLimit>0?View.VISIBLE:View.GONE);
        chart.drawingMode(0);activeSummary=new JSONObject();chart.setData(Collections.emptyList(),new JSONArray());chart.setAudit(null);chart.setOverlays(null);
    }
    private void setFullscreen(boolean enabled){
        fullscreen=enabled;status.setVisibility(enabled?View.GONE:View.VISIBLE);diagnostic.setVisibility(enabled?View.GONE:View.VISIBLE);
        if(enabled)getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
    }
    private void chartSettings(){
        new AlertDialog.Builder(this).setTitle("차트 설정")
            .setItems(new String[]{fullscreen?"전체화면 해제":"전체화면","EMA 20/60/200 "+(ema?"끄기":"켜기"),"볼린저밴드 20·2σ "+(bands?"끄기":"켜기"),"보조지표 선택","전체 범위 600봉","상세 진단"},(d,i)->{
                if(i==0)setFullscreen(!fullscreen);
                if(i==1)ema=!ema;
                if(i==2)bands=!bands;
                if(i==3)new AlertDialog.Builder(this).setTitle("가격 차트 아래 보조창")
                    .setSingleChoiceItems(new String[]{"거래량만","RSI(14) 참고지표","ADX(14) 참고지표","전략 정규화 거래량"},indicatorPane,(a,k)->{indicatorPane=k;chart.options(ema,bands,indicatorPane);saveWorkspace();a.dismiss();}).show();
                if(i==4){width=600;zoomWidth=600;offset=Math.max(0,Math.min(offset,availableBars()-width));load();}
                if(i==5)showDiagnostic();
                chart.options(ema,bands,indicatorPane);saveWorkspace();
            }).setNegativeButton("닫기",null).show();
    }
    private void showDataQuality(){
        if(loading||busy){status.setText("데이터를 불러오는 중입니다.");return;}
        StringBuilder message=new StringBuilder(warning.getText()).append("\n\n표시 구간만 검사 · 전략 신호 준비 판정과 다릅니다.\n");
        message.append("4거래소 동일봉 유효 거래량: ").append(dataQuality.optInt("four_exchange_complete")).append(" / ").append(dataQuality.optInt("bars"));
        message.append("\n누락 봉: ").append(dataQuality.optInt("missing_bars")).append(" · 불규칙 간격: ").append(dataQuality.optInt("irregular_intervals"));
        message.append("\nOHLC 오류: ").append(dataQuality.optInt("invalid_ohlc")).append(" · 거래량 오류: ").append(dataQuality.optInt("invalid_volume"));
        JSONObject exchanges=dataQuality.optJSONObject("exchanges");
        if(exchanges!=null)for(String ex:new String[]{"binance","bitget","okx","bybit"}){
            JSONObject row=exchanges.optJSONObject(ex);if(row==null)continue;
            message.append("\n\n").append(ex).append(" · 누락 ").append(row.optInt("missing")).append(" · 중복 ").append(row.optInt("duplicate")).append(" · 거래량 오류 ").append(row.optInt("invalid_volume")).append(" · 0 거래량 ").append(row.optInt("zero_volume"));
        }
        message.append("\n\n주황색 띠 = 주의 봉. 길게 누르고 이동하면 봉을 살펴봅니다.\n거래량 0은 관측값이며 데이터 누락과 구분합니다. SMA 워밍업 충족 여부는 전략 진단에서 확인하세요.");
        JSONArray rows=dataQuality.optJSONArray("rows");
        if(rows!=null&&rows.length()>0){message.append("\n\n주의 봉 예시 (최대 20개, UTC)");java.text.SimpleDateFormat fmt=new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm",Locale.US);fmt.setTimeZone(TimeZone.getTimeZone("UTC"));for(int i=0;i<Math.min(20,rows.length());i++){JSONObject row=rows.optJSONObject(i);message.append("\n").append(fmt.format(new Date(row.optLong("timestamp")))).append(" · ").append(row.optJSONArray("reasons"));}}
        ScrollView scroll=new ScrollView(this);TextView text=new TextView(this);text.setText(message.toString());text.setTextIsSelectable(true);text.setPadding(dp(16),dp(12),dp(16),dp(12));scroll.addView(text);
        new AlertDialog.Builder(this).setTitle("차트 데이터 검사").setView(scroll).setPositiveButton("닫기",null).show();
    }
    private void pauseReplay(){playing=false;playback.removeCallbacks(playbackTick);}
    private void setReplay(int limit){
        pauseReplay();replayLimit=Math.max(1,Math.min(total,limit));offset=Math.max(0,replayLimit-width);
        generation.incrementAndGet();activeSummary=new JSONObject();trades=new JSONArray();auditPage=new JSONObject();
        chart.setData(Collections.emptyList(),trades);chart.setAudit(null);chart.setOverlays(null);diagnostic.setText("리플레이 준비 중 · 미래 데이터 숨김");
        status.setText("리플레이");modeText.setText("REPLAY · 미래 봉/청산 숨김");replayBar.setVisibility(View.VISIBLE);load();
    }
    private void stepReplay(int amount){
        if(busy||market==null||replayLimit<=0)return;
        if(amount<0){setReplay(replayLimit+amount);return;}
        replayLimit=Math.max(1,Math.min(total,replayLimit+amount));offset=Math.max(0,replayLimit-width);pendingInspect=0;load();
    }
    private void replayMenu(){
        if(blocked()||market==null)return;
        pauseReplay();
        new AlertDialog.Builder(this).setTitle("과거 봉 리플레이 · 실거래 아님")
            .setItems(new String[]{"처음 200봉부터 시작","선택한 봉부터 시작","리플레이 종료"},(d,i)->{
                if(i==0)setReplay(Math.min(total,200));
                if(i==2){replayLimit=0;replayBar.setVisibility(View.GONE);load();}
                if(i==1){
                    long timestamp=chart.selectedTime();String[] m=market.clone();int request=generation.incrementAndGet();
                    worker.execute(()->{try(SQLiteDatabase db=SQLiteDatabase.openDatabase(m[0],null,SQLiteDatabase.OPEN_READONLY);
                        Cursor c=db.rawQuery("SELECT count(*) FROM ohlcv WHERE asset_class='crypto' AND exchange=? AND symbol=? AND timeframe=? AND timestamp<=?",new String[]{m[1],m[2],m[3],""+timestamp})){
                        c.moveToFirst();int n=c.getInt(0);runOnUiThread(()->{if(!disposed&&request==generation.get())setReplay(n);});
                    }catch(Exception e){error(e);}});
                }
            }).setNegativeButton("닫기",null).show();
    }
    private void navigateTrade(int direction){
        if(loading)return;
        long current=chart.selectedTime(),target=direction>0?Long.MAX_VALUE:Long.MIN_VALUE;
        for(int i=0;i<trades.length();i++){
            JSONObject t=trades.optJSONObject(i);if(t==null)continue;
            long time=CandleChartView.millis(t.optString("entry_time"));
            if(direction>0&&time>current&&time<target)target=time;
            if(direction<0&&time<current&&time>target)target=time;
        }
        if(target==Long.MAX_VALUE||target==Long.MIN_VALUE){status.setText("해당 방향에 확인 가능한 거래가 없습니다.");return;}
        pauseReplay();jump(target);
    }
    @Override public void drawing(JSONObject shape){
        if(annotations.length()>=100){status.setText("그리기는 시장별 최대 100개입니다.");return;}
        annotations.put(shape);chart.setDrawings(visibleAnnotations(chart.selectedTime()));saveWorkspace();status.setText("그리기 저장됨 · 주문/알림이 아닌 차트 메모입니다.");
    }
    private JSONArray visibleAnnotations(long cutoff){
        if(replayLimit<=0)return annotations;
        JSONArray visible=new JSONArray();
        for(int i=0;i<annotations.length();i++){JSONObject item=annotations.optJSONObject(i);if(item!=null&&item.optLong("time")<=cutoff&&item.optLong("time2",0)<=cutoff)visible.put(item);}
        return visible;
    }
    private void chartTools(){
        if(market==null)return;pauseReplay();
        new AlertDialog.Builder(this).setTitle("차트 도구")
            .setItems(new String[]{"수평선 · 가격 터치","추세선 · 두 점 터치","그리기 취소","마지막 그리기 삭제","선택 봉 북마크","북마크로 이동","차트 PNG 저장","전략 JSON 저장","거래 CSV 저장"},(d,i)->{
                if(i==0||i==1){chart.drawingMode(i+1);status.setText(i==0?"가격 차트에서 수평선 위치를 터치하세요.":"추세선의 시작점과 끝점을 터치하세요.");}
                if(i==2)chart.drawingMode(0);
                if(i==3){if(annotations.length()>0)annotations.remove(annotations.length()-1);chart.setDrawings(visibleAnnotations(chart.selectedTime()));saveWorkspace();}
                if(i==4)bookmark();
                if(i==5)showBookmarks();
                if(i==6)exportChart();
                if(i==7)exportStrategy();
                if(i==8)exportTrades();
            }).setNegativeButton("닫기",null).show();
    }
    private void bookmark(){
        if(chart.selectedTime()==0)return;
        long time=chart.selectedTime();EditText title=new EditText(this);title.setHint("메모");title.setText("확인할 봉");
        new AlertDialog.Builder(this).setTitle("선택 봉 북마크").setView(title).setPositiveButton("저장",(d,i)->{
            if(bookmarks.length()>=100){status.setText("북마크는 시장별 최대 100개입니다.");return;}
            try{bookmarks.put(new JSONObject().put("time",time).put("label",title.getText().toString()));saveWorkspace();}catch(JSONException ignored){}
        }).setNegativeButton("취소",null).show();
    }
    private void showBookmarks(){
        ArrayList<JSONObject> visible=new ArrayList<>();ArrayList<String> labels=new ArrayList<>();
        for(int i=0;i<bookmarks.length();i++){JSONObject b=bookmarks.optJSONObject(i);if(b==null||replayLimit>0&&b.optLong("time")>chart.selectedTime())continue;visible.add(b);labels.add(b.optString("label")+" · "+new Date(b.optLong("time")).toString());}
        if(visible.isEmpty()){status.setText("현재 확인할 수 있는 북마크가 없습니다.");return;}
        new AlertDialog.Builder(this).setTitle("북마크 선택").setItems(labels.toArray(new String[0]),(d,i)->jump(visible.get(i).optLong("time")))
            .setNeutralButton("모두 삭제",(d,i)->new AlertDialog.Builder(this).setMessage("이 시장의 북마크를 모두 삭제할까요?").setPositiveButton("삭제",(a,k)->{bookmarks=new JSONArray();saveWorkspace();}).setNegativeButton("취소",null).show()).setNegativeButton("닫기",null).show();
    }
    private void showPerformance(){
        pauseReplay();
        if(replayLimit>0){new AlertDialog.Builder(this).setMessage("리플레이에서는 미래 정보를 포함한 전체 수익률과 성과를 숨깁니다. 현재까지 청산된 거래만 거래 표에서 확인하세요.").setPositiveButton("확인",null).show();return;}
        if(activeSummary.length()==0){new AlertDialog.Builder(this).setMessage("먼저 이 DB에 전략을 적용하거나 저장된 결과를 선택하세요.").setPositiveButton("결과 선택",(d,i)->chooseResult()).setNegativeButton("닫기",null).show();return;}
        JSONObject summary=activeSummary;
        LinearLayout content=new LinearLayout(this);content.setOrientation(1);content.setPadding(dp(12),dp(10),dp(12),dp(10));content.setBackgroundColor(Color.rgb(16,19,24));
        TextView metrics=new TextView(this);metrics.setTextColor(Color.WHITE);metrics.setTextSize(14);
        metrics.setText("수익률 "+num(summary,"return_percent")+"% · MDD "+num(summary,"max_drawdown_percent")+"%"
            +"\n순손익 "+num(summary,"pnl")+" USDT · 승률 "+num(summary,"win_rate")+"%"
            +"\n거래 "+summary.optInt("trades")+" · PF "+num(summary,"profit_factor")+" · 청산 "+summary.optInt("liquidations")
            +"\n추정 비용 "+num(summary,"estimated_costs")+" USDT"
            +"\n"+summary.optString("requested_start")+" ~ "+summary.optString("requested_end")
            +"\n"+summary.optString("execution_model")+" · "+(summary.optBoolean("compounding_enabled")?"복리":"고정 자산")+" · 곡선은 요약 표시");
        content.addView(metrics);
        Button monthly=new Button(this);monthly.setText("월별 실현손익");monthly.setOnClickListener(v->showMonthly(summary.optJSONArray("trades_log")));content.addView(monthly);
        JSONArray equity=summary.optJSONArray("equity_curve"),sample=new JSONArray();
        if(equity!=null){int stride=Math.max(1,(equity.length()+1199)/1200);for(int i=0;i<equity.length();i+=stride)sample.put(equity.optJSONObject(i));if(equity.length()>0)sample.put(equity.optJSONObject(equity.length()-1));}
        BacktestChartView performance=new BacktestChartView(this);performance.setData(sample,trades);content.addView(performance,new LinearLayout.LayoutParams(-1,dp(360)));
        ScrollView scroll=new ScrollView(this);scroll.addView(content);
        new AlertDialog.Builder(this).setTitle("전략 성과 · 순자산/낙폭").setView(scroll)
            .setPositiveButton("저장 결과 선택",(d,i)->chooseResult()).setNeutralButton("거래 CSV",(d,i)->exportTrades()).setNegativeButton("닫기",null).show();
    }
    private void exportText(String name,String mime,String text){
        if(blocked())return;exportText=text;
        startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType(mime).addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,name),EXPORT_TEXT);
    }
    private void showMonthly(JSONArray log){
        TreeMap<String,double[]> months=new TreeMap<>();
        if(log!=null)for(int i=0;i<log.length();i++){
            JSONObject trade=log.optJSONObject(i);if(trade==null)continue;String time=trade.optString("exit_time");
            if(time.length()<7)continue;String month=time.substring(0,7);double[] value=months.get(month);
            if(value==null){value=new double[3];months.put(month,value);}
            double pnl=trade.optDouble("pnl");value[0]++;if(pnl>0)value[1]++;value[2]+=pnl;
        }
        TableLayout table=new TableLayout(this);table.setBackgroundColor(Color.rgb(16,19,24));
        TableRow header=new TableRow(this);for(String title:new String[]{"월 UTC","거래","승률 %","순손익 USDT"})cell(header,title,true);table.addView(header);
        for(Map.Entry<String,double[]> item:months.descendingMap().entrySet()){
            double[] value=item.getValue();TableRow row=new TableRow(this);
            for(String text:new String[]{item.getKey(),String.valueOf((int)value[0]),String.format(Locale.US,"%.2f",value[1]/value[0]*100),String.format(Locale.US,"%+.2f",value[2])})cell(row,text,false);
            table.addView(row);
        }
        ScrollView vertical=new ScrollView(this);vertical.addView(table);HorizontalScrollView horizontal=new HorizontalScrollView(this);horizontal.addView(vertical);
        new AlertDialog.Builder(this).setTitle("월별 실현손익 · 청산일 기준").setView(horizontal).setNegativeButton("닫기",null).show();
    }
    private void exportStrategy(){
        if(strategyParameters.isEmpty()||market==null){status.setText("저장할 전략이 없습니다.");return;}
        try{
            JSONObject document=new JSONObject().put("symbol",market[2]).put("timeframe",market[3]).put("parameters",new JSONObject(strategyParameters));
            exportText("strategy-"+market[3]+".json","application/json",document.toString(2));
        }catch(Exception e){error(e);}
    }
    private String csv(String value){
        if(value==null)value="";
        String trimmed=value.trim();
        if(!trimmed.isEmpty()&&"=+-@".indexOf(trimmed.charAt(0))>=0){
            try{if(!Double.isFinite(Double.parseDouble(trimmed)))value="'"+value;}
            catch(NumberFormatException e){value="'"+value;}
        }
        return "\""+value.replace("\"","\"\"")+"\"";
    }
    private void exportTrades(){
        if(trades.length()==0){status.setText("내보낼 청산 거래가 없습니다.");return;}
        String[] keys={"trade","side","entry_time","exit_time","avg_entry_price","exit_price","tp_price","sl_price","qty","pnl","reason"};
        StringBuilder out=new StringBuilder("\uFEFF");out.append(String.join(",",keys)).append("\r\n");
        for(int i=0;i<trades.length();i++){JSONObject t=trades.optJSONObject(i);if(t==null)continue;for(int k=0;k<keys.length;k++){if(k>0)out.append(',');out.append(csv(t.optString(keys[k],"")));}out.append("\r\n");}
        exportText(replayLimit>0?"replay-closed-trades.csv":"backtest-trades.csv","text/csv",out.toString());
    }
    private void exportChart(){
        if(blocked()||chart.getWidth()==0||chart.getHeight()==0)return;
        if(exportBitmap!=null)exportBitmap.recycle();
        exportBitmap=Bitmap.createBitmap(chart.getWidth(),chart.getHeight()+dp(32),Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(exportBitmap);canvas.drawColor(Color.rgb(16,19,24));
        android.graphics.Paint caption=new android.graphics.Paint(3);caption.setColor(Color.CYAN);caption.setTextSize(dp(12));
        canvas.drawText(modeText.getText().toString(),dp(8),dp(20),caption);canvas.translate(0,dp(32));chartFrame.draw(canvas);
        startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("image/png").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,"db-chart.png"),EXPORT_IMAGE);
    }
    private void editStrategy(){
        if(blocked())return;
        if(strategyParameters.isEmpty()){
            worker.execute(()->{try{JSONObject preset=new JSONObject(python().getModule("universal_bot.chart_workspace").callAttr("preset").toString());
                runOnUiThread(()->{if(!disposed){strategyParameters=preset.optJSONObject("parameters").toString();editStrategy();}});
            }catch(Exception e){error(e);}});return;
        }
        try{
            JSONObject draft=new JSONObject(strategyParameters);LinearLayout fields=new LinearLayout(this);fields.setOrientation(1);fields.setPadding(dp(14),dp(8),dp(14),dp(8));
            TextView hint=new TextView(this);hint.setText("DB 백테스트용 수치입니다. LIVE 설정은 바뀌지 않습니다.\n진입 890% = 자산 8.9배 · 변경 후 다시 계산해야 차트에 반영됩니다.");fields.addView(hint);
            Map<String,View> inputs=new LinkedHashMap<>();ArrayList<String> keys=new ArrayList<>();
            for(Iterator<String> i=draft.keys();i.hasNext();){String key=i.next();Object value=draft.opt(key);if(value instanceof Boolean||value instanceof Number||value instanceof String)if(!key.equals("entry_multiplier"))keys.add(key);}
            Collections.sort(keys);
            for(String key:keys){
                Object value=draft.opt(key);
                if(value instanceof Boolean){Switch input=new Switch(this);input.setText(parameterLabel(key));input.setChecked((Boolean)value);fields.addView(input);inputs.put(key,input);}
                else{
                    TextView label=new TextView(this);label.setText(parameterLabel(key));fields.addView(label);
                    if(key.equals("backtest_execution_model")){
                        Spinner input=new Spinner(this);input.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"signal_close","next_open"}));input.setSelection("next_open".equals(value)?1:0);fields.addView(input);inputs.put(key,input);
                    }else{EditText input=new EditText(this);input.setSingleLine(true);input.setText(String.valueOf(value));fields.addView(input);inputs.put(key,input);}
                }
            }
            ScrollView scroll=new ScrollView(this);scroll.addView(fields);
            AlertDialog dialog=new AlertDialog.Builder(this).setTitle("전략 수치 편집 · DB 검증").setView(scroll).setPositiveButton("저장 · 재계산",null).setNegativeButton("취소",null).create();
            dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
                try{
                    for(String key:keys){
                        View input=inputs.get(key);Object previous=draft.opt(key);
                        if(input instanceof Switch)draft.put(key,((Switch)input).isChecked());
                        else if(input instanceof Spinner)draft.put(key,((Spinner)input).getSelectedItem().toString());
                        else {String value=((EditText)input).getText().toString().trim();
                            if(previous instanceof Number){double n=Double.parseDouble(value);if(!Double.isFinite(n))throw new IllegalArgumentException(parameterLabel(key)+" 값 오류");
                                if(previous instanceof Integer||previous instanceof Long){if(n!=Math.rint(n))throw new IllegalArgumentException(parameterLabel(key)+"는 정수입니다.");draft.put(key,(long)n);}else draft.put(key,n);
                            }else draft.put(key,value);
                        }
                    }
                    if(draft.has("order_percent_of_equity"))draft.put("entry_multiplier",draft.optDouble("order_percent_of_equity")/100.0);
                    strategyParameters=draft.toString();if(market!=null)prefs().edit().putString("chart_parameters:"+market[0],strategyParameters).apply();dialog.dismiss();confirmStrategy(strategyParameters);
                }catch(Exception e){new AlertDialog.Builder(this).setMessage("입력값 확인: "+e.getMessage()).setPositiveButton("확인",null).show();}
            }));
            dialog.show();
        }catch(Exception e){error(e);}
    }
    private String parameterLabel(String key){
        String[][] names={{"volume_lookback","거래량 평균 봉"},{"volume_break_multiplier","거래량 돌파 배수"},{"min_one_bar_vol","1봉 변동 최소 %"},{"max_one_bar_vol","1봉 변동 최대 %"},{"volatility_bars","TP/SL 변동성 기준 봉"},{"tp_vol_multiplier","TP 변동성 배수"},{"sl_vol_multiplier","SL 변동성 배수"},{"min_tp_percent","최소 TP %"},{"max_tp_percent","최대 TP %"},{"min_sl_percent","최소 SL %"},{"max_sl_percent","최대 SL %"},{"use_nbar_volatility_block","N봉 급변동 차단"},{"nbar_volatility_bars","N봉 차단 기간"},{"max_nbar_volatility","N봉 최대 변동 %"},{"use_rsi_filter","RSI 필터"},{"rsi_length","RSI 기간"},{"rsi_oversold_min","LONG RSI 최소"},{"rsi_oversold_max","LONG RSI 최대"},{"rsi_overbought_min","SHORT RSI 최소"},{"rsi_overbought_max","SHORT RSI 최대"},{"use_adx_filter","ADX 필터"},{"adx_length","ADX 기간"},{"adx_min","ADX 최소"},{"adx_max","ADX 최대"},{"cooldown_bars","진입 후 쿨다운"},{"reentry_bars","청산 후 재진입 대기"},{"initial_capital","초기자산 USDT"},{"order_percent_of_equity","진입 규모 % (890 = 8.9배)"},{"leverage","최대 레버리지"},{"backtest_compounding_enabled","복리"},{"backtest_execution_model","체결: 신호봉 종가 / 다음 봉 시가"},{"backtest_fee_percent","편도 수수료 %"},{"backtest_slippage_percent","편도 슬리피지 %"},{"allow_long","LONG 허용"},{"allow_short","SHORT 허용"},{"max_pyramiding","최대 진입 횟수"},{"first_entry_consecutive_candles","첫 진입 연속봉"},{"block_weekend","주말 차단"},{"excluded_hours","제외 시간 UTC"},{"adaptive_regime_enabled","시장 국면 자동전환"}};
        for(String[] item:names)if(item[0].equals(key))return item[1];return key;
    }

    @Override protected void onPause(){saveWorkspace();pauseReplay();super.onPause();}
    @Override public void onBackPressed(){if(fullscreen){setFullscreen(false);return;}super.onBackPressed();}
    @Override protected void onDestroy(){disposed=true;pauseReplay();if(cancelFile!=null)try{cancelFile.createNewFile();}catch(IOException ignored){}generation.incrementAndGet();worker.shutdownNow();super.onDestroy();}
}
