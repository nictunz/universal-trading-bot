package com.nictunz.universalbacktester;

import android.app.*;
import android.content.Context;
import android.widget.*;
import java.util.*;
import java.text.SimpleDateFormat;

/** Symbol, interval and requested UTC-day range in one chart entry point. */
public final class ChartMarketPicker {
    public interface Selection { void open(String symbol,String timeframe,String start,String end); }
    public static void show(Activity activity,String currentSymbol,String currentTimeframe,Selection selection){
        LinearLayout body=new LinearLayout(activity);body.setOrientation(1);int padding=(int)(16*activity.getResources().getDisplayMetrics().density);body.setPadding(padding,padding,padding,padding);
        TextView hint=new TextView(activity);hint.setText("USDT 무기한 선물 · Bitget 가격 / 4거래소 거래량\n저장 DB 우선 · 부족한 구간 자동 다운로드\nWi-Fi·모바일 데이터 모두 사용");body.addView(hint);
        AutoCompleteTextView coin=new AutoCompleteTextView(activity);coin.setSingleLine(true);coin.setHint("코인 검색 · 예: BTC, ETH, SOL");coin.setThreshold(1);coin.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_dropdown_item_1line,new String[]{"BTC","ETH","SOL","XRP","BNB","DOGE","ADA","AVAX","LINK","DOT","SUI","LTC"}));coin.setText(currentSymbol==null?"BTC":currentSymbol.split("/")[0]);coin.setOnClickListener(v->coin.showDropDown());body.addView(coin);
        TextView tfLabel=new TextView(activity);tfLabel.setText("봉 주기");body.addView(tfLabel);
        String[] values={"1m","3m","5m","15m","30m","1h","4h","1d"};String[] labels={"1분","3분","5분","15분","30분","1시간","4시간","1일"};
        Spinner tf=new Spinner(activity);tf.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_spinner_dropdown_item,labels));tf.setSelection(Math.max(0,Arrays.asList(values).indexOf(currentTimeframe==null?"15m":currentTimeframe)));body.addView(tf);
        Calendar end=Calendar.getInstance(TimeZone.getTimeZone("UTC"));end.set(Calendar.HOUR_OF_DAY,0);end.set(Calendar.MINUTE,0);end.set(Calendar.SECOND,0);end.set(Calendar.MILLISECOND,0);end.add(Calendar.DATE,-1);long latest=end.getTimeInMillis();Calendar start=(Calendar)end.clone();start.add(Calendar.DATE,-29);
        SimpleDateFormat fmt=new SimpleDateFormat("yyyy-MM-dd",Locale.US);fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        Button from=new Button(activity),to=new Button(activity);Runnable refresh=()->{from.setText("시작 · "+fmt.format(start.getTime()));to.setText("종료 · "+fmt.format(end.getTime()));};
        HorizontalScrollView presets=new HorizontalScrollView(activity);LinearLayout buttons=new LinearLayout(activity);String[] names={"1주","1개월","3개월","1년","3년","5년"};int[] days={7,30,90,365,1095,1825};
        for(int i=0;i<days.length;i++){final int amount=days[i];Button b=new Button(activity);b.setText(names[i]);b.setOnClickListener(v->{end.setTimeInMillis(latest);start.setTimeInMillis(latest);start.add(Calendar.DATE,1-amount);refresh.run();});buttons.addView(b);}presets.addView(buttons);body.addView(presets);
        from.setOnClickListener(v->pick(activity,start,latest,refresh));to.setOnClickListener(v->pick(activity,end,latest,refresh));body.addView(from);body.addView(to);refresh.run();
        TextView note=new TextView(activity);note.setText("완료된 UTC 날짜 기준 · 어제까지 선택 가능\n지원하지 않는 코인이나 상장 전 기간은 데이터 부족으로 표시됩니다.");body.addView(note);
        ScrollView scroll=new ScrollView(activity);scroll.addView(body);
        AlertDialog dialog=new AlertDialog.Builder(activity).setTitle("시장 선택").setView(scroll).setPositiveButton("차트 열기",null).setNegativeButton("취소",null).create();dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            String symbol=coin.getText().toString().trim().toUpperCase(Locale.US).replace("/USDT:USDT","");if(symbol.endsWith("USDT"))symbol=symbol.substring(0,symbol.length()-4);
            if(!symbol.matches("[A-Z0-9]{2,20}")){coin.setError("코인 심볼을 입력하세요");return;}
            long range=(end.getTimeInMillis()-start.getTimeInMillis())/86400000L+1;if(range<1||range>3660){Toast.makeText(activity,"기간은 1일~10년 사이로 선택하세요",Toast.LENGTH_LONG).show();return;}
            selection.open(symbol+"/USDT:USDT",values[tf.getSelectedItemPosition()],fmt.format(start.getTime()),fmt.format(end.getTime()));dialog.dismiss();
        }));dialog.show();
    }
    private static void pick(Activity a,Calendar date,long latest,Runnable changed){DatePickerDialog picker=new DatePickerDialog(a,(v,y,m,d)->{date.set(y,m,d);changed.run();},date.get(Calendar.YEAR),date.get(Calendar.MONTH),date.get(Calendar.DAY_OF_MONTH));picker.getDatePicker().setMaxDate(latest);picker.show();}
}
