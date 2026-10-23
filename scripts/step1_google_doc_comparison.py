"""Prepare dated NAV comparisons and concise Google Docs content from saved runs."""
import hashlib
import html
import json
import os
from pathlib import Path
import shutil

os.environ['MPLCONFIGDIR']='/private/tmp/portfolio-step1-mpl'
os.environ['XDG_CACHE_HOME']='/private/tmp/portfolio-step1-cache'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/step1/paper_period/google_doc_20261006'
OUT.mkdir(exist_ok=True)
OLD=ROOT/'outputs/step1/portfolio_static/historical_replay_daily_returns_nav.csv'
NEW=ROOT/'outputs/step1/paper_period/corrected/trusted_baseline_nav.csv'
METRICS=ROOT/'outputs/step1/paper_period/corrected/trusted_baseline_metrics.csv'
NAMES={'EW':'Equal Weight','MVO':'MVO','BL':'BL+ML','HYBRID':'Hybrid'}
old=pd.read_csv(OLD,parse_dates=['date'])
new=pd.read_csv(NEW,parse_dates=['date'])
metrics=pd.read_csv(METRICS)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'axes.spines.top':False,'axes.spines.right':False})
rows=[]
daily=[]

for phase,scenario,start in [('IS','historical_is_default','2020-02-11'),('OOS','historical_oos_default','2023-10-02')]:
    historic=old[old.scenario==scenario].set_index('date').sort_index()
    # Replay exports earned-return dates only. The historical OOS anchor is
    # explicitly declared by its audited source ledger, not inferred from NAV.
    if phase=='OOS':
        anchor=pd.DataFrame({s+'_NAV':[1.] for s in NAMES},index=[pd.Timestamp(start)])
        historic=pd.concat([anchor,historic]).sort_index()
    fig,axes=plt.subplots(2,2,figsize=(6.5,5.1),sharex=True)
    for ax,s in zip(axes.flat,NAMES):
        prior=historic[s+'_NAV'].dropna().loc[start:]
        current=new[(new.phase==phase)&(new.strategy==s)].set_index('date').nav.sort_index().loc[start:]
        assert prior.index[0]==current.index[0]==pd.Timestamp(start)
        prior=prior/prior.iloc[0]
        current=current/current.iloc[0]
        common=prior.index.intersection(current.index)
        assert common[0]==pd.Timestamp(start) and len(common)>100
        a,b=prior.loc[common],current.loc[common]
        r1,r2=a.pct_change().dropna(),b.pct_change().dropna()
        relative=b/a-1
        record={'phase':phase,'strategy':s,'common_anchor':start,'common_end':str(common[-1].date()),
            'n_common_nav_dates':len(common),'n_common_return_intervals':len(r1),
            'return_correlation':float(r1.corr(r2)),'log_nav_correlation':float(np.log(a).corr(np.log(b))),
            'paper_nav_at_common_end':float(a.iloc[-1]),'rerun_nav_at_common_end':float(b.iloc[-1]),
            'relative_terminal_nav_gap':float(relative.iloc[-1]),'max_absolute_relative_nav_gap':float(relative.abs().max()),
            'date_of_max_relative_gap':str(relative.abs().idxmax().date()),
            'rerun_nav_at_requested_end_on_comparison_anchor':float(current.iloc[-1]),
            'paper_source_end':str(prior.index[-1].date()),'rerun_source_end':str(current.index[-1].date())}
        rows.append(record)
        for when in common:
            daily.append({'phase':phase,'strategy':s,'date':when,'paper_replay_nav':float(a.loc[when]),
                'rerun_nav':float(b.loc[when]),'relative_nav_gap':float(relative.loc[when])})
        ax.plot(prior.index,prior.values,color='#bd6b12',linestyle='--',linewidth=1.6,label='Paper (replay)')
        ax.plot(current.index,current.values,color='#1267b1',linewidth=1.6,label='Run Apr 2026')
        if phase=='OOS':
            ax.axvspan(prior.index[-1],current.index[-1],color='#b7b7b7',alpha=.18)
            ax.axvline(prior.index[-1],color='#555',linestyle=':',linewidth=.9)
        ax.set_title(NAMES[s],fontweight='bold')
        ax.set_ylabel('NAV')
        ax.grid(alpha=.2)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.tick_params(axis='x',labelbottom=True)
        ax.set_xlim(current.index[0],current.index[-1])
    fig.suptitle(f'{phase} NAV comparison   |   anchor {start}',fontweight='bold',fontsize=11.5)
    handles,labels=axes.flat[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.945),ncol=2,frameon=False,fontsize=9)
    footer='NAV = 1 at the common start. Paper curve reconstructed from archived weights.'
    if phase=='OOS':footer+='\nShaded period after 27 Feb 2026: rerun only.'
    fig.text(.5,.014,footer,ha='center',fontsize=7,color='#444')
    fig.tight_layout(rect=[0,.065,1,.89])
    fig.savefig(OUT/f'paper_vs_rerun_{phase.lower()}.png',dpi=200)
    fig.savefig(OUT/f'paper_vs_rerun_{phase.lower()}.svg')
    plt.close(fig)

summary=pd.DataFrame(rows)
summary.to_csv(OUT/'trajectory_comparison.csv',index=False)
pd.DataFrame(daily).to_csv(OUT/'trajectory_common_dates.csv',index=False)

def esc(x):return html.escape(str(x))
def p(x):return '<p>'+x+'</p>'
def table(headers,values):
    head='<tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr>'
    body=''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in values)
    return '<table border="1" cellspacing="0" cellpadding="5" style="border-collapse:collapse;width:100%;font-family:Arial;font-size:10pt;border-color:#d9d9d9">'+head+body+'</table>'
def fragment(body):
    return '<html><head><meta charset="utf-8"></head><body style="font-family:Arial;font-size:11pt;color:#000;line-height:1.25">'+body+'</body></html>'

main_table=[]
for x in metrics.itertuples():
    main_table.append([x.phase,NAMES[x.strategy],f'{x.final_nav:.4f}',f'{100*x.ann_return:.2f}%',f'{100*x.ann_volatility:.2f}%',f'{x.sharpe:.3f}',f'{100*x.max_drawdown:.2f}%'])
first='<h1 style="font-size:20pt;color:#000">Báo cáo Step 1 kết quả chạy lại và đối chiếu với paper</h1>'
first+=p('Cập nhật ngày 06/10/2026. Kỳ chạy lại: 01/2020–04/2026; chia IS/OOS tại 01/10/2023. Đã kiểm chứng phép tính và tái lập kết quả, nhưng chưa đủ bằng chứng để chứng nhận đầy đủ dữ liệu lịch sử.')
first+='<h2 style="font-size:14pt;color:#000">1 Kết quả chạy lại</h2>'
first+=p('Mẫu chung có 1.573 phiên và 32 tài sản (30 cổ phiếu, GOLD, VFF). IS ghi nhận 911 return từ 11/02/2020 đến 29/09/2023 sau khởi tạo; OOS ghi nhận 641 return từ 02/10/2023 đến 29/04/2026. Ngày 30/04 là mốc hết tháng yêu cầu; phiên cuối có dữ liệu là 29/04.')
first+=table(['Kỳ','Chiến lược','NAV cuối','LN/năm','Vol/năm','Sharpe','MDD'],main_table)
first+=p('NAV bắt đầu bằng 1 ở mỗi kỳ. Vol/năm là độ lệch chuẩn return ngày × √252; Sharpe dùng return vượt lãi suất phi rủi ro ngày, quy đổi theo 252 phiên/năm. Chi phí giao dịch bằng 0.')
first+=p('<b>Nhận xét:</b> BL+ML giảm biến động và drawdown so với MVO. Hybrid tăng lợi nhuận so với BL+ML nhưng chịu rủi ro cao hơn. Sharpe Hybrid 1,648 so với BL+ML 1,629 chưa có kiểm định ý nghĩa thống kê.')
first+='<h2 style="font-size:14pt;color:#000">2 So sánh đường NAV với paper</h2>'
first+=p('Đường “Paper (replay)” được tái dựng từ target weights đã lưu của snapshot 71cc107; terminal NAV khớp số công bố ở độ chính xác hiển thị. Đây là replay phép tính, không phải huấn luyện lại mô hình paper gốc. Log OOS kết thúc 27/02/2026 dù văn bản paper ghi tháng 4; Figure 1 lại ghi tháng 3. Không kéo dài đường paper bằng dữ liệu tự bổ sung.')
first+=p('<b>Hình 1. Đường NAV trong IS.</b> Hai chuỗi được chuẩn hóa NAV=1 tại 11/02/2020 và so sánh đến 29/09/2023. Việc chuẩn hóa phục vụ so sánh hình dạng; số cuối có thể khác bảng hiệu suất do mốc khởi tạo paper sớm hơn.')
(OUT/'part1.html').write_text(fragment(first))

second=p('<b>Hình 2. Đường NAV trong OOS.</b> Hai chuỗi được chuẩn hóa NAV=1 tại 02/10/2023. Phần nền xám sau 27/02/2026 chỉ có đường chạy lại. Bảng hiệu suất dùng mốc NAV OOS của bản sửa tại 29/09/2023 nên điểm cuối biểu đồ có thể khác nhẹ số trong bảng.')
(OUT/'part2.html').write_text(fragment(second))

comparison=[]
for x in summary.itertuples():
    comparison.append([x.phase,NAMES[x.strategy],f'{x.return_correlation:.3f}',f'{100*x.relative_terminal_nav_gap:+.2f}%',f'{100*x.max_absolute_relative_nav_gap:.2f}%'])
third='<h3 style="font-size:12pt;color:#000">Mức tương đồng trên khoảng thời gian chung</h3>'
third+=table(['Kỳ','Chiến lược','Corr return','Chênh NAV cuối','Chênh NAV lớn nhất'],comparison)
third+=p('Corr return là Pearson giữa return từ hai NAV tại cùng các mốc ngày quan sát. Chênh NAV = NAV mới/NAV paper − 1 sau chuẩn hóa cùng mốc; cột cuối lấy trị tuyệt đối lớn nhất. IS so sánh 11/02/2020–29/09/2023; OOS so sánh 02/10/2023–27/02/2026. Các khoảng ngày giống nhau; input snapshots và mechanics vẫn khác. Đây không phải kiểm định tái tạo chính xác hoặc ablation một thành phần.')
third+=p('<b>Kết luận về đường đi:</b> EW gần như trùng ở cả IS/OOS. Trong OOS, MVO có NAV cuối 27/02 gần bằng paper nhưng từng lệch 15,81% trong kỳ; chỉ nhìn điểm cuối sẽ bỏ sót khác biệt này. BL+ML và Hybrid có tương quan return lần lượt 0,933 và 0,911; NAV cuối khoảng chung cao hơn paper 6,68% và 5,04%. Các đợt tăng/giảm lớn tương đồng, nhưng chưa tái tạo đúng toàn bộ đường NAV.')
third+=p('Trong IS, MVO từng lệch 45,54% dù chênh cuối khoảng chung chỉ −1,89%; BL+ML/Hybrid cuối khoảng chung thấp hơn 8,87%/13,49%. Kết quả thể hiện khác biệt đáng kể của đường tích lũy sau khi đổi dữ liệu và sửa mechanics, không quy riêng cho một thành phần.')
third+='<h2 style="font-size:14pt;color:#000">3 Những lỗi đã xử lý</h2>'
third+=p('Baseline đã dùng VFF xác minh đúng productId21, một nguồn GOLD nhất quán và lịch phiên VNINDEX; loại nhãn fitting chồng vào validation, đồng bộ trạng thái feature giữa fit/inference, chuyển thực thi sang close phiên kế tiếp, giữ số đơn vị tài sản giữa các giao dịch và kiểm ràng buộc sau cleanup. Crawler gốc/vnstock vẫn được giữ nguyên; nếu tải lại bằng nhánh cũ, lỗi gán mã quỹ có thể tái diễn.')
third+=p('27/27 regression tests và 52/52 kiểm tra độc lập đạt; không có vi phạm target-weight constraints vượt tolerance1e−8. Hai lượt April fit mới cho13CSV và dự báo giống hoàn toàn. Turnover OOS/năm: EW0,623; MVO23,822; BL+ML8,630; Hybrid16,868 vòngNAV/năm.')
third+='<h2 style="font-size:14pt;color:#000">4 Vấn đề còn mở và kết luận</h2>'
third+=p('Chưa xác minh lịch sử công bố/sửa đổi NAV VFF và giá GOLD; GOLD còn thiếu metadata quote/đơn vị/địa điểm; cổ phiếu chưa rõ điều chỉnh chia tách/cổ tức. Môi trường và artifacts mô hình của lượt paper gốc chưa đủ để tái tạo độc lập toàn bộ. Nguồn gốc lựa chọn tham số trước OOS cũng chưa có bằng chứng đầy đủ.')
third+=p('Paper cần đồng bộ mốc thời gian và mô tả Sharpe, view transformation, penalty rủi ro với actual code. Dòng alpha_normal1 vẫn pha BL khi stress/crisis (alpha0,3/0,1), nên chênh MVO3,73 với Hybrid3,57 không phải một lỗi chữ đơn thuần. Universe vẫn cố định và chi phí bằng0; xử lý ở Step7/8. Hit rate rawOOS51,02% và emittedviews50,43% dùng denominator khác nhau, không suy ra giá trị kinh tế riêng của ML.')
third+=p('<b>Đã kiểm chứng phép tính và tái lập baseline; chưa chứng nhận đầy đủ tính nhân quả của dữ liệu lịch sử. Ưu tiên xác minh thời điểm công bố/điều chỉnh giá và thống nhất bảng, hình, phương pháp của paper.</b>')
third+=p('Nguồn: PDF CSoNet2026 ML Enhanced Black Litterman Final; archived-target-weight replay snapshot71cc107; run corrected-paper-period-20261004T132742 và repeat133908. Đối chiếu đường đi thực hiện ngày06/10/2026 từ các artifacts đã lưu, không fit hoặc tune thêm mô hình.')
third+=p('<b>NOT READY FOR STEP 2</b>')
(OUT/'part3.html').write_text(fragment(third))

provenance={'analysis_kind':'Read-only analysis of stored runs; no ML fitting, tuning or strategy execution',
    'target_google_doc':'https://docs.google.com/document/d/17Hzm6ND3ZB8UioSkeqZVP3ysJEpQslEaDxTwwPXBKKw/edit?tab=t.0',
    'date':'2026-10-06','source_files':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [OLD,NEW,METRICS]],
    'actual_run_id':'corrected-paper-period-20261004T132742','historic_kind':'Archived-target-weight replay, not independently regenerated models',
    'OOS_anchor_added_from_verified_ledger':'2023-10-02 NAV=1',
    'alignment':'Exact NAV-date intersection; rebase each curve at the same explicit date; no backfill/forward-fill/synthetic paper extension',
    'correlation_definition':'Pearson on NAV percentage changes computed on identical common timestamps; an interval can span exchange holidays',
    'comparison_limit':'Different source snapshots, calendars and integrity fixes. No isolated ML-value or statistical significance claim',
    'similarity_records':rows}
(OUT/'comparison_provenance.json').write_text(json.dumps(provenance,indent=2))
print(summary.to_string(index=False))
