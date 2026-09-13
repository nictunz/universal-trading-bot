package com.nictunz.universalbacktester;

import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.*;
import java.util.*;

/** Chart overlay using real trace values; never evaluates signals independently. */
public class StrategyDiagnosticPanel extends LinearLayout {
    public static final int PASS=Color.rgb(81,220,143), FAIL=Color.rgb(244,91,110),
        NEUTRAL=Color.rgb(193,202,216), INFO=Color.rgb(70,192,212), FIXED=Color.rgb(244,206,85);
    private final TextView header;
    private final ScrollView scroll;
    private final LinearLayout body;
    private final List<TextView[]> cells=new ArrayList<>();
    private boolean collapsed;
    private int corner;
    public StrategyDiagnosticPanel(Context c){
        super(c);setOrientation(VERTICAL);
        GradientDrawable bg=new GradientDrawable();bg.setColor(Color.argb(242,12,16,23));bg.setStroke(dp(1),Color.rgb(95,109,129));setBackground(bg);
        collapsed=c.getSharedPreferences("chart_panel",0).getBoolean("collapsed",false);
        corner=c.getSharedPreferences("chart_panel",0).getInt("corner",0);
        header=new TextView(c);header.setTextColor(INFO);header.setTextSize(13);header.setPadding(dp(10),dp(9),dp(8),dp(9));header.setBackgroundColor(Color.rgb(28,39,55));addView(header);
        body=new LinearLayout(c);body.setOrientation(VERTICAL);body.setPadding(dp(6),dp(3),dp(6),dp(6));
        scroll=new ScrollView(c);scroll.addView(body);addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        header.setOnClickListener(v->{collapsed=!collapsed;save();resize();});
        header.setOnLongClickListener(v->{PopupMenu menu=new PopupMenu(c,header);String[] names={"오른쪽 위","왼쪽 위","오른쪽 아래","왼쪽 아래"};for(int i=0;i<4;i++)menu.getMenu().add(0,i,i,names[i]);menu.setOnMenuItemClickListener(item->{corner=item.getItemId();save();resize();return true;});menu.show();return true;});
        setRows(Collections.singletonList(new String[]{"상태","전략을 적용하세요",String.valueOf(NEUTRAL)}));
    }
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private void save(){getContext().getSharedPreferences("chart_panel",0).edit().putBoolean("collapsed",collapsed).putInt("corner",corner).apply();}
    public void resize(){
        if(!(getParent() instanceof FrameLayout))return;
        FrameLayout parent=(FrameLayout)getParent();int w=parent.getWidth(),h=parent.getHeight();if(w<=0||h<=0)return;
        FrameLayout.LayoutParams lp=new FrameLayout.LayoutParams(Math.min(dp(340),Math.max(dp(140),(int)(w*.72f))),collapsed?dp(38):Math.max(dp(38),Math.min(dp(555),h-dp(70))));
        lp.gravity=(corner%2==0?Gravity.RIGHT:Gravity.LEFT)|(corner<2?Gravity.TOP:Gravity.BOTTOM);lp.setMargins(dp(6),dp(44),dp(6),dp(22));
        setLayoutParams(lp);scroll.setVisibility(collapsed?GONE:VISIBLE);header.setText(collapsed?"전략 진단 ▾":"전략 진단 · DB  ▴");
    }
    public void setRows(List<String[]> rows){
        while(cells.size()<rows.size()){
            LinearLayout row=new LinearLayout(getContext());row.setPadding(0,dp(4),0,dp(4));
            TextView label=new TextView(getContext()),value=new TextView(getContext());label.setTextSize(12);value.setTextSize(12);label.setTextColor(NEUTRAL);value.setGravity(Gravity.RIGHT);value.setMaxLines(3);
            row.addView(label,new LinearLayout.LayoutParams(0,-2,.38f));row.addView(value,new LinearLayout.LayoutParams(0,-2,.62f));body.addView(row);cells.add(new TextView[]{label,value});
        }
        for(int i=0;i<cells.size();i++){TextView[] pair=cells.get(i);((LinearLayout)pair[0].getParent()).setVisibility(i<rows.size()?VISIBLE:GONE);if(i>=rows.size())continue;String[] r=rows.get(i);pair[0].setText(r[0]);pair[1].setText(r[1]);pair[1].setTextColor(Integer.parseInt(r[2]));}
    }
}
