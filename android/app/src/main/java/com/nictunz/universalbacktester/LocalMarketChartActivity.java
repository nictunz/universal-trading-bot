package com.nictunz.universalbacktester;

import android.app.*;
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
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
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
                market=markets.get(pos);total=Integer.parseInt(market[4]);offset=Math.max(0,total-width);trades=new JSONArray();load();
            }
        });
        root.addView(bar);
        status=new TextView(this);status.setTextColor(Color.LTGRAY);status.setTextSize(12);status.setPadding(dp(10),0,dp(10),0);status.setText("저장된 코인 DB 검색 중…");root.addView(status);
        chart=new CandleChartView(this,this);root.addView(chart,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout actions=new LinearLayout(this);
        addButton(actions,"날짜",()->{Calendar now=Calendar.getInstance();new DatePickerDialog(this,(v,y,m,d)->jumpDate(y,m,d),now.get(Calendar.YEAR),now.get(Calendar.MONTH),now.get(Calendar.DAY_OF_MONTH)).show();});
        addButton(actions,"최근",()->{offset=Math.max(0,total-width);load();});
        addButton(actions,"거래",this::showTrades);
        addButton(actions,"결과",this::chooseResult);
        root.addView(actions);setContentView(root);
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
                if(databaseFiles.isEmpty()){databaseSelector.setText("DB 선택");status.setText("다운로드한 DB가 없습니다. 백테스터에서 코인 DB를 먼저 받으세요.");return;}
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
        if(database==null)return;
        selectedDatabasePath=database.getAbsolutePath();
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
        if(market==null||disposed)return;
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
                JSONObject s=loadedResult;boolean match=matches(s,m);JSONArray log=match?s.optJSONArray("trades_log"):null;
                JSONArray data=log==null?new JSONArray():log;
                String msg=match?String.format(Locale.US,"수익 %.2f%% · MDD %.2f%% · %d거래",s.optDouble("return_percent"),s.optDouble("max_drawdown_percent"),data.length()):"캔들 보기 · ‘결과’에서 이 DB의 백테스트를 선택하세요";
                if(data.length()>0&&!data.optJSONObject(0).has("tp_price"))msg+=" · TP/SL 선은 재실행 후 표시";
                final String message=msg;
                runOnUiThread(()->{if(disposed||request!=generation.get())return;trades=data;chart.setData(rows,data);status.setText(message+"\n드래그 이동 · 두 손가락 확대 · 터치 OHLC · UTC");});
            }catch(Exception e){runOnUiThread(()->{if(!disposed&&request==generation.get())status.setText("차트 읽기 실패: "+e.getMessage());});}
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
        if(trades.length()==0){new AlertDialog.Builder(this).setMessage("선택한 DB의 백테스트 결과를 먼저 선택하세요.").setPositiveButton("확인",null).show();return;}
        String[] labels=new String[trades.length()];for(int i=0;i<labels.length;i++){JSONObject t=trades.optJSONObject(i);labels[i]="#"+t.optInt("trade",i+1)+" "+t.optString("side")+"  "+t.optString("entry_time")+"\n"+t.optString("reason")+"  "+String.format(Locale.US,"%+.2f USDT",t.optDouble("pnl"));}
        new AlertDialog.Builder(this).setTitle("거래 선택 → 해당 캔들 이동").setItems(labels,(d,i)->jump(CandleChartView.millis(trades.optJSONObject(i).optString("entry_time")))).setNegativeButton("닫기",null).show();
    }
    private void chooseResult(){
        if(market==null)return;String[] m=market.clone();
        worker.execute(()->{
            ArrayList<File> files=new ArrayList<>();collect(new File(getFilesDir(),"UniversalTradingBotCache"),".json",files,4);
            ArrayList<File> valid=new ArrayList<>();ArrayList<String> labels=new ArrayList<>();
            files.sort((a,b)->Long.compare(b.lastModified(),a.lastModified()));
            for(File f:files){if(!f.getName().contains("backtest"))continue;try{JSONObject s=readResult(f.getAbsolutePath());if(matches(s,m)&&s.optJSONArray("trades_log")!=null){valid.add(f);labels.add(f.getName()+"\n"+s.optString("requested_start")+" ~ "+s.optString("requested_end"));}}catch(Exception ignored){}}
            runOnUiThread(()->{if(disposed||market!=null&&!Arrays.equals(m,market))return;if(valid.isEmpty()){status.setText("이 DB에 연결된 결과가 없습니다. 백테스트 실행 후 다시 선택하세요.");return;}
                new AlertDialog.Builder(this).setTitle("백테스트 실행 선택").setItems(labels.toArray(new String[0]),(d,i)->{resultPath=valid.get(i).getAbsolutePath();load();}).setNegativeButton("닫기",null).show();});
        });
    }
    @Override protected void onDestroy(){disposed=true;generation.incrementAndGet();worker.shutdownNow();super.onDestroy();}
}
