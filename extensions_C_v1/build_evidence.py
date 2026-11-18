"""Build derived evidence/report from an explicit completed C run; never rerun optimizers."""
from pathlib import Path
import argparse,json,shutil,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .C1_fixed_rule import HERE,C1,B_NAMES,ANCHOR
from experiments_core.src.frozen import sha,write_json

NAMES={C1:'C1 fixed rule','B1_BLnoML':'B1 prior-only','B2_BLML':'B2 BL + ML'}
COLORS=['#555555','#2678B2','#DF7D28']

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,row))+' |' for row in rows])


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='extensions-C-20261104T210906');p.add_argument('--repeat',default='extensions-C-20261104T211105');a=p.parse_args()
    run=HERE/'runs'/a.run;out=run/'outputs';repeat=HERE/'runs'/a.repeat
    assert json.loads((run/'manifest.json').read_text())['status']=='succeeded'
    files=sorted(out.glob('*.csv'));assert all(f.read_bytes()==(repeat/'outputs'/f.name).read_bytes() for f in files)
    for f in files:shutil.copy2(f,HERE/f.name)
    for item in json.loads((HERE/'baseline_manifest.json').read_text())['files']:
        assert sha(Path(item['source']))==sha(HERE/'inputs'/item['snapshot'])==item['sha256']
    metrics=pd.read_csv(out/'C1_results.csv');daily=pd.read_csv(out/'C1_daily.csv',parse_dates=['date']);exposure=pd.read_csv(out/'C1_class_exposures.csv',parse_dates=['date'])
    l1=pd.read_csv(out/'target_L1_distances.csv',parse_dates=['execution_date']);ci=pd.read_csv(out/'paired_uncertainty.csv')
    oos=metrics[(metrics.phase=='OOS')&(metrics.bps_per_side==0)].set_index('strategy')
    fig=HERE/'figures';fig.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    f,ax=plt.subplots(figsize=(10,4))
    for color,name in zip(COLORS,[C1]+B_NAMES):
        x=daily[(daily.strategy==name)&(daily.date>=ANCHOR)]
        ax.plot(x.date,x.gross_nav_continuous/x.gross_nav_continuous.iloc[0],label=NAMES[name],color=color,lw=1.6)
    ax.set(ylabel='Gross NAV, OOS anchor = 1',title='C1 fixed weighting is close to frozen B1');ax.legend();ax.grid(alpha=.15);f.tight_layout();f.savefig(fig/'C1_OOS_wealth.png',dpi=170);plt.close(f)
    f,ax=plt.subplots(figsize=(10,3.6))
    for color,name in zip(COLORS,[C1]+B_NAMES):
        x=metrics[(metrics.phase=='OOS')&(metrics.strategy==name)]
        ax.plot(x.bps_per_side,x.sharpe,'o-',label=NAMES[name],color=color)
    ax.set(xlabel='Hypothetical bps per traded side',ylabel='OOS net Sharpe',title='Turnover determines sensitivity to hypothetical costs');ax.legend();ax.grid(alpha=.15);f.tight_layout();f.savefig(fig/'C1_cost_sensitivity.png',dpi=170);plt.close(f)
    f,axes=plt.subplots(3,1,figsize=(10,6),sharex=True)
    for ax,name in zip(axes,[C1]+B_NAMES):
        x=exposure[(exposure.strategy==name)&(exposure.weight_type=='start_of_return_drifted')&(exposure.date>ANCHOR)]
        ax.stackplot(x.date,x.equities,x.GOLD,x.VFF,labels=['Equities','GOLD proxy','VFF proxy'],colors=['#2678B2','#D6AE32','#7DAB80'],alpha=.85)
        target=exposure[(exposure.strategy==name)&(exposure.weight_type=='execution_target')&(exposure.date>ANCHOR)]
        ax.plot(target.date,target.VFF,'k:',lw=.8,label='VFF target')
        ax.set(ylim=(0,1),ylabel=NAMES[name]);ax.grid(alpha=.1)
    axes[0].legend(loc='upper left',ncol=4,fontsize=8);axes[0].set_title('Drifted class exposures; dotted line = VFF execution target')
    f.tight_layout();f.savefig(fig/'C1_class_weights.png',dpi=170);plt.close(f)
    events=pd.read_csv(out/'selected_k5_events.csv',parse_dates=['decision_date','assumed_execution_date'])
    # One heatmap row per equity, one column per decision; exact dated selector, no hindsight fill.
    tickers=sorted(set(events[[f'ticker_{i}' for i in range(1,6)]].stack()));mask=np.array([[t in row for row in events[[f'ticker_{i}' for i in range(1,6)]].values] for t in tickers])
    f,ax=plt.subplots(figsize=(10,4.6));ax.imshow(mask,aspect='auto',interpolation='nearest',cmap='Blues',vmin=0,vmax=1)
    ax.set_yticks(range(len(tickers)),tickers,fontsize=8);indices=np.linspace(0,len(events)-1,7).astype(int);ax.set_xticks(indices,events.decision_date.iloc[indices].dt.strftime('%Y-%m'),fontsize=9)
    ax.axvline(np.searchsorted(events.decision_date.values,ANCHOR.to_datetime64())-.5,color='#DF7D28',lw=1)
    ax.set(title='Frozen Proposed K5 membership at each decision',xlabel='Decision date; orange line = OOS boundary');f.tight_layout();f.savefig(fig/'C1_dated_membership.png',dpi=170);plt.close(f)
    # Explicit C2 stop artifacts, no zero returns or invented metrics.
    c2={'strategy':'VN30TRI','status':'NOT_RUN_SOURCE_GATE_NOT_MET','N':0,'final_nav':None,'ann_return':None,'ann_volatility':None,'sharpe':None,'max_drawdown':None,'turnover':None,'reason':'No accepted daily levels with vendor_record_date, historical vintage and research-use evidence'}
    pd.DataFrame([c2]).to_csv(HERE/'C2_results.csv',index=False)
    pd.DataFrame(columns=['return_date','index_identifier','index_return','B1_gross_return','B2_gross_return']).to_csv(HERE/'C2_market_daily.csv',index=False)
    cal=daily[(daily.strategy==C1)&(daily.date>ANCHOR)].date
    pd.DataFrame({'return_date':cal,'status':'NOT_EVALUABLE_NO_ACCEPTED_SERIES'}).to_csv(HERE/'C2_unmatched_dates.csv',index=False)
    (HERE/'C2_source_and_alignment.md').write_text('''# C2 source and alignment status\n\nNOT RUN: source gate not met. Candidate VN30TRI; expected anchor 2023-09-29, 641 portfolio returns 2023-10-02–2026-04-29. Accepted source level rows: 0; aligned returns: 0. All 641 dates are not evaluable because no accepted series was supplied, not because verified market observations are missing on those dates. See C2_unmatched_dates.csv. No interpolation, zero filling or replacement with VNINDEX price return. C2_results.csv is a status row with null metrics; C2_market_daily.csv contains a header only.\n\nIdentity and gross dividend-reinvestment definition verified from HOSE/SSC documentation; daily level file, vendor_record_date, complete historical vintage/change record and explicit research-use evidence remain absent. See C2_source_feasibility.md and C2_source_audit.json for source URLs and findings.\n\nFuture approved input: C2_market.py checks metadata, freezes local inputs/hashes before calculation, rejects duplicate/nonpositive/unsorted observations, never bridges a missing session, and chooses the longest contiguous daily common sample (earliest tie). B1/B2 are recomputed and all three paths re-anchored on the same prior session. Index turnover is N/A; gross index is descriptive, not an executable same-constraint benchmark.\n''')
    policy=json.loads((HERE/'inputs/availability_policy.json').read_text());prices=pd.read_csv(HERE/'inputs/prices_valuation.csv',index_col=0)
    manifest=json.loads((HERE/'baseline_manifest.json').read_text());panelsha=next(x['sha256'] for x in manifest['files'] if x['snapshot']=='prices_valuation.csv')
    source={x['asset']:x for x in policy['source_rows']};dictionary=[]
    for ticker in prices:
        kind='provider_native_adjusted_close' if ticker not in ['GOLD','VFF'] else 'archival_close_sell' if ticker=='GOLD' else 'fund_NAV'
        dictionary.append({'ticker':ticker,'currency':'VND','unit':'thousand_VND_per_share' if ticker not in ['GOLD','VFF'] else 'thousand_VND_per_luong' if ticker=='GOLD' else 'thousand_VND_per_fund_unit',
                           'series_type':kind,'source':source[ticker]['kind'],'raw_source_sha256':source[ticker]['sha256'],'valuation_panel_sha256':panelsha,
                           'first_date':prices.index[0],'last_date':prices.index[-1],'historical_first_publication_verified':False,
                           'provider_record_dates':'not fully supplied; use inherited availability ledger, not invented historical release dates',
                           'return_type':'provider-native adjusted price, cash-dividend total-return status not independently certified' if ticker not in ['GOLD','VFF'] else 'valuation proxy return',
                           'raw_redistribution_permitted':False})
    pd.DataFrame(dictionary).to_csv(HERE/'input_dictionary.csv',index=False)
    enriched=events.copy();enriched['effective_selection_date']=enriched.groupby('selection_state_id').assumed_execution_date.transform('min')
    enriched.to_csv(HERE/'selected_k5_events.csv',index=False)
    enriched[['decision_index','decision_date','assumed_execution_date','selection_state_id','effective_selection_date']].to_csv(HERE/'rebalance_calendar.csv',index=False)
    (HERE/'data_dictionary.md').write_text('''# Input/output data dictionary\n\nExact private input snapshots and original source paths/SHA256: baseline_manifest.json. Raw matrix prices_valuation.csv is date × 32 tickers; source, series_type, currency, unit, adjustment convention and known publication limitations are recorded per ticker in input_dictionary.csv. prices_eligible.csv is the separate decision-information matrix. availability_ledger.csv records session_date, asset, observed_at, available_at, availability_basis and source. Modeled timestamps are not certified first-public releases. Original provider-record/publication history is incomplete; no value is invented. C1 is conditional on the accepted frozen proxy-availability contract; claims requiring verified PIT or actual execution stop here. C2 is stopped until its independent source pack exists.\n\nEquities: KBS provider-native adjusted integer close /1000 (thousand VND/share), no additional cash dividend. GOLD: archived SJC-HCM selling close, thousand VND/luong, approximate source resolution 100000 VND; next-calendar-day eligibility. VFF: FMarket product 21, original NAV /1000, thousand VND/fund unit; five observed-session buffer plus later provider metadata. Check original raw identity hash in input_dictionary.csv. Dates/calendar inherited from frozen observed Vietnamese sessions; no new calendar invented.\n\nselected_k5_events.csv (root export) adds effective_selection_date = first assumed execution using that selection_state_id. The immutable run export is retained without this later convenience column. rebalance_calendar.csv preserves all 310 decisions/fills, state IDs and initial/terminal dates. Membership history_end is strictly before decision_date.\n\nC1_daily.csv: one row per strategy/date; continuous IS→OOS gross/net NAV, gross and cost-scenario daily return. First anchor return is empty. Re-anchor each phase at its recorded preceding valuation date for reported phase metrics; do not use full-period wealth as OOS NAV. Holdings: three *_holdings_weights.csv, weights at start of the indexed return. C1_units.csv stores post-close units; unit × valuation price plus cash reconstructs wealth.\n\nC1_trades.csv: one row per asset × event × strategy (all 32 assets, including zero positions). pre_trade_weight, target_weight, weight_change are asset-specific. turnover, traded_notional and event_cost_fraction_* are EVENT-LEVEL values repeated on each asset row: deduplicate by strategy/execution_date before summing them. Full traded notional = sum absolute weight changes = 2 × one-way turnover, including cash deployment convention; initial deployment excluded from annual TO. Initial cost charged once IS; terminal event charged.\n\nC1_results.csv: phase IS/OOS, 0/10/25/50 bps per traded side; ann_return/volatility/MDD are fractions, Sharpe and HHI dimensionless, turnover portfolio-equivalent one-way trades/year, final_nav starts at 1 per phase. N=906/641. mean_effective_holdings = mean(1/daily HHI) over positive-investment return days, not inverse of mean HHI. Target HHI applies at execution, daily HHI at start of return.\n\ncomparisons.csv includes all 16 phase × pair × cost combinations and 4 metrics each; CAGR/MDD differences are percentage points. paired_uncertainty.csv is gross OOS only, block10 noncircular paired returns, 1000 draws, seed20261104. No refitting. Raw prices and vendor histories excluded from upload; a licensed local input pack is necessary for a fresh simulation.\n''')
    # Original log attachments are copied verbatim; do not rewrite run manifest retrospectively.
    for r,label in [(run,'primary'),(repeat,'repeat')]:
        for stream in ['stdout','stderr']:
            original=HERE/f'C1_{label}_{stream}.log'
            if original.exists():shutil.copy2(original,r/f'{stream}.log')
    checks=json.loads((run/'validation.json').read_text())
    write_json(HERE/'reproduction_check.json',{'status':'PASS','primary_run':a.run,'repeat_run':a.repeat,'identical_numerical_csv_files':len(files),'source_inputs_unchanged':True,'core_checks':checks,
              'C2_status':'NOT_RUN_SOURCE_GATE_NOT_MET','note':'C1 source/tests snapshots are the pre-result versions; later report/C2/test additions are recorded in publication manifest'})
    def perf(phase):
        x=metrics[(metrics.phase==phase)&(metrics.bps_per_side==0)]
        return table(['Nhánh','NAV','CAGR %','Vol %','Sharpe','MDD %','TO/năm'],[[NAMES[r.strategy],f'{r.final_nav:.4f}',f'{100*r.ann_return:.2f}',f'{100*r.ann_volatility:.2f}',f'{r.sharpe:.3f}',f'{100*r.max_drawdown:.2f}',f'{r.annualized_turnover:.3f}'] for r in x.itertuples()])
    concentration=table(['Nhánh','HHI target','HHI daily','Số vị thế hiệu dụng'],[[NAMES[n],f'{oos.loc[n].mean_target_HHI:.6f}',f'{oos.loc[n].mean_daily_HHI:.6f}',f'{oos.loc[n].mean_effective_holdings:.3f}'] for n in [C1]+B_NAMES])
    costs=table(['Nhánh','S 0 bps','S 10 bps','S 25 bps','S 50 bps','NAV 50 bps'],[[NAMES[n]]+[f'{metrics[(metrics.strategy==n)&(metrics.phase=="OOS")&(metrics.bps_per_side==b)].iloc[0].sharpe:.3f}' for b in [0,10,25,50]]+[f'{metrics[(metrics.strategy==n)&(metrics.phase=="OOS")&(metrics.bps_per_side==50)].iloc[0].final_nav:.4f}'] for n in [C1]+B_NAMES])
    uncertainty=table(['Cặp','Chỉ số','Hiệu ứng','CI 95%'],[['C1 − '+('B1' if r.right==B_NAMES[0] else 'B2'),'CAGR (điểm %)' if r.metric=='ann_return' else 'Sharpe',f'{r.effect:+.3f}',f'[{r.ci_low:+.3f}; {r.ci_high:+.3f}]'] for r in ci.itertuples()])
    report=f'''# Báo cáo thí nghiệm bổ sung C
C1: đối chứng tỷ trọng cố định khả thi · C2: thẩm định nguồn chỉ số tổng thu nhập

Ngày thực hiện: 04/11/2026. Phiên bản C-v1. Mã chạy chính: {a.run}; chạy lặp: {a.repeat}. Báo cáo độc lập với việc chỉnh sửa bản thảo A+B.

## 1. Kết luận chính và phạm vi

C1 đã hoàn tất trên đúng lịch và danh mục bảy công cụ của B1/B2. Quy tắc đơn giản VFF 30%, mỗi cổ phiếu trong năm mã được chọn và GOLD 11,6667% tạo kết quả OOS gần B1: CAGR 23,66% so với 23,49%; Sharpe 1,172 so với 1,175. B2 có Sharpe gross cao hơn, nhưng lợi thế quan sát được nhạy với chi phí do turnover lớn. Các khoảng tin cậy chênh lệch đều chứa 0; chưa đủ bằng chứng xác định hướng hiệu ứng trong tổng thể.

C2 hoàn tất phần tìm nguồn và đánh giá tính khả thi theo điều kiện dừng của đề bài. Chưa có chuỗi chỉ số tổng thu nhập hằng ngày đáp ứng đồng thời yêu cầu dữ liệu, vintage và quyền sử dụng. Vì vậy không tính thành tích chỉ số và không đưa ra kết luận vượt thị trường. Đây là thí nghiệm chưa chạy số liệu, không phải kết quả chỉ số bằng 0. C3–C6 chỉ có đề cương, chưa triển khai.

C1 trả lời giá trị bổ sung của cách phân bổ, với bộ chọn Proposed K5 được giữ cố định. Nó không kiểm định riêng hiệu quả của bộ chọn cổ phiếu, không phải chiến lược mua và giữ vô điều kiện, và không xác lập alpha. Giai đoạn OOS này đã được xem trong dự án trước đây; C là mở rộng sau thiết kế trên holdout đã quan sát, không phải OOS độc lập mới hay đăng ký trước mang tính triển vọng.

## 2. Dữ liệu kế thừa và giao thức cố định

Giữ nguyên baseline availability-observed-contract-20261012T233110 của Step 1 và core-evidence-20261023T211011 của Step 2. Các snapshot đầu vào được đối chiếu SHA256 trước/sau chạy; B1/B2 được dựng lại từ tỷ trọng đã lưu, không tối ưu lại và không huấn luyện ML. Tất cả chỉ số và bốn kịch bản chi phí B1/B2 khớp hồ sơ đóng băng trong sai số dưới 1e-10.

IS: mốc NAV 18/02/2020, 906 return đến 29/09/2023. OOS: mốc NAV 29/09/2023, 641 return từ 02/10/2023 đến 29/04/2026. Giữ đường nắm giữ liên tục qua ranh giới IS/OOS; chỉ chuẩn hóa NAV từng kỳ khi báo cáo. Tái cân bằng mỗi năm phiên, chọn lại theo lịch Proposed K5 đã lưu; toàn mẫu có 78 trạng thái chọn và 310 sự kiện giao dịch.

Giao thức protocol_frozen.md và mã nguồn được lưu/hash trước khi tính kết quả C1. Quy tắc, cadence, lưới phí và bootstrap seed 20261104 không được điều chỉnh sau khi thấy thành tích. Hai lượt chạy độc lập cho kết quả giống từng byte ở 12 file CSV số liệu. Các bổ sung trình bày và kiểm thử C2 về sau được ghi riêng trong publication_manifest.json, không thay bản snapshot của C1.

Dữ liệu định giá có 30 cổ phiếu cố định cộng GOLD và VFF. Cổ phiếu dùng giá điều chỉnh của KBS; không tự cộng thêm cổ tức. Chưa có lịch sử revision/corporate actions đủ để xác nhận total return của từng mã. GOLD là giá bán SJC-HCM lưu trữ; VFF là NAV FMarket product 21. Mốc công bố lịch sử thực tế còn thiếu; kế thừa ledger và giả định availability đã chấp nhận, không gán ngày công bố mới. C1 chỉ có ý nghĩa có điều kiện theo hợp đồng proxy này, không chứng nhận dữ liệu point-in-time hoàn chỉnh hay khả năng khớp lệnh.

## 3. C1 được hiện thực như thế nào

Tại quyết định t, lấy trạng thái Proposed K5 gần nhất có selection_date không muộn hơn t và history_end trước t. Đặt VFF = 0,30; mỗi cổ phiếu được chọn và GOLD = 0,70/6; mọi mã còn lại bằng 0. Tổng trọng số bằng 1, không bán khống, không mã nào quá 0,50 và nhóm ngoài VFF bằng 0,70, dung sai 1e-8. Mỗi menu còn được kiểm tra trực tiếp với audit B1 và B2 ở cùng ngày.

Vị thế cũ nhận biến động t→t+1 trước khi thực hiện target tại giá đóng cửa giả định t+1. Vị thế mới chỉ nhận return t+1→t+2. Giữ số đơn vị tài sản và cho trọng số trôi giữa các lần giao dịch; xử lý mua/bán trên hợp 32 mã nên không bỏ sót mã rời danh mục. Tính TO sự kiện bằng nửa tổng trị tuyệt đối chênh lệch target với trọng số trước giao dịch. TO năm = 252 × tổng TO / N, loại lần cấp vốn đầu. Chi phí lần đầu chỉ tính trong IS; không cấp vốn lại ở đầu OOS; giao dịch cuối kỳ vẫn bị tính phí mà không thêm return tương lai.

Quy ước chỉ số: CAGR = NAV cuối^(252/N) − 1; biến động năm dùng độ lệch chuẩn mẫu ddof=1 nhân căn 252; Sharpe dùng rf ngày = 1,06^(1/252) − 1. MDD có dấu âm. TO 0,760 nghĩa là khoảng 0,760 lần giá trị danh mục được thay đổi một chiều trong một năm theo quy ước này, không phải 0,760%.

## 4. Kết quả gross: C1 so với B1/B2

OOS, trước chi phí, cùng 641 return và cùng mốc NAV = 1:

{perf('OOS')}

C1 hơn B1 khoảng 0,168 điểm phần trăm CAGR nhưng thấp hơn 0,0025 Sharpe. TO C1 thấp hơn B1 khoảng 10,7%. B2 hơn C1 khoảng 3,002 điểm phần trăm CAGR và 0,195 Sharpe gross, đồng thời TO cao khoảng 10,5 lần. Đây là quan sát trên mẫu cụ thể, không chứng minh mức tăng kỳ vọng trong tương lai.

IS, cùng 906 return:

{perf('IS')}

Trong IS, C1 thấp hơn B1 một ít về CAGR/Sharpe; B2 cũng không đứng đầu. Cả kết quả thuận lợi và bất lợi được giữ nguyên. Không chọn lại trọng số C1 hoặc mô hình B2 để cải thiện xếp hạng.

![Hình 1. NAV gross OOS, chuẩn hóa tại 29/09/2023; C1 và B1 gần nhau.](figures/C1_OOS_wealth.png)

## 5. Độ tập trung và cơ chế phân bổ

{concentration}

HHI target = tổng bình phương trọng số ở lần thực hiện. Với VFF ít nhất 30% và sáu phần còn lại chia đều, mức HHI nhỏ nhất là 0,30² + 6 × (0,70/6)² = 0,1716667. Quy tắc C1 đạt mức này ở mỗi target. HHI daily tính trên trọng số đã trôi ở đầu ngày return; có thể thấp hơn mốc lý thuyết của target vì VFF tạm trôi xuống dưới 30% giữa các lần tái cân bằng. Số vị thế hiệu dụng là trung bình của 1/HHI theo ngày đã đầu tư, không phải 1 chia HHI trung bình.

Khoảng cách L1 giữa target C1 và B1 trung bình OOS là 0,021493, tối đa 0,038344; nghĩa là tổng độ lệch tuyệt đối khoảng 2,149 điểm phần trăm trọng số, tương đương khoảng 1,075% tái phân bổ một chiều giữa hai target đầy đủ đầu tư. Với B2, L1 trung bình là 0,506589. Hai target B1/C1 gần nhau nhưng không trùng; HHI gần nhau cũng không tự chứng minh cùng danh mục hoặc cùng lợi nhuận.

Kết quả này làm hẹp cách diễn giải B1: kết quả gross tốt không tự chứng minh prior BL đã tạo thêm giá trị kinh tế rõ rệt so với một quy tắc khả thi đơn giản trên cùng menu. Đồng thời, C1 vẫn thừa hưởng chọn mã Proposed K5 và cơ hội GOLD/VFF; không thể dùng nó để kết luận bộ chọn hoặc tài sản ngoài cổ phiếu không cần thiết.

![Hình 2. Tỷ trọng lớp tài sản đã trôi ở đầu return; nét chấm là target VFF tại ngày thực hiện.](figures/C1_class_weights.png)

![Hình 3. Lịch thành viên Proposed K5 cố định theo quyết định; vạch cam là ranh giới OOS.](figures/C1_dated_membership.png)

## 6. Chi phí giả định và khoảng bất định

Chi phí theo mỗi phía mua hoặc bán là 0/10/25/50 bps; 1 bps = 0,01 điểm phần trăm. Mỗi sự kiện áp hệ số (1 − c × tổng absolute traded weights) lên tăng trưởng gross trong ngày thực hiện. Đây là xấp xỉ kế thừa trên giao dịch gross, không phải mô phỏng holdings chính xác sau phí hoặc phí quỹ, spread vàng và lịch nhận lệnh thực tế.

{costs}

Ở 10 bps, B2 có Sharpe 1,251, cao hơn mức khoảng 1,16 của C1/B1. Ở 25 và 50 bps, C1/B1 có Sharpe cao hơn B2. Trong bốn kịch bản đã định, C1 chỉ nhỉnh hơn B1 về Sharpe ở 25 và 50 bps; chênh lệch nhỏ và không được biến thành tuyên bố vượt trội chắc chắn. Không suy ra ngưỡng hòa vốn chính xác từ vài điểm lưới; không dùng kết quả để chọn chi phí có lợi.

![Hình 4. Sharpe OOS sau chi phí giả định; B2 nhạy với turnover hơn C1/B1.](figures/C1_cost_sensitivity.png)

Bootstrap ghép cặp gross OOS dùng moving blocks không vòng, độ dài 10 ngày, 1.000 mẫu lặp, seed 20261104. Trong mỗi cặp, cả hai chuỗi lấy cùng chỉ số ngày; chỉ lấy mẫu return đã lưu, không huấn luyện lại. CI là percentile 95%, CAGR chênh lệch tính bằng điểm phần trăm.

{uncertainty}

Tất cả CI chứa 0. Chưa đủ bằng chứng xác định hướng hiệu ứng; không đồng nghĩa các phương pháp tương đương và không xác nhận alpha. CI có điều kiện theo cửa sổ, universe, selector và nguồn dữ liệu cố định; không bao quát rủi ro chọn thiết kế sau khi thấy holdout, survivorship hoặc vintage nguồn chưa hoàn chỉnh.

## 7. C2: kết quả thẩm định nguồn và điều kiện dừng

Ứng viên đã định trước là VN30TRI chính thức, sau đó mới xét một biến thể VN-Index total return nếu có thể xác minh. Factsheet HOSE tháng 06/2026 xác nhận VN30TRI là chỉ số tổng thu nhập cuối ngày bằng VND. Quy tắc HOSE v1.2 lưu trên SSC, mục 5A, mô tả tái đầu tư cổ tức tiền mặt theo ex-date. Đây là xác minh danh tính/định nghĩa, chưa phải bộ lịch sử hằng ngày có vintage và quyền sử dụng phù hợp.

Trang TradingView cho thấy mã HOSE:VN30TRI nhưng chưa cung cấp gói daily được chấp nhận; trang CEIC đã xem là chuỗi tháng; tài liệu market-breadth của FiinQuant nhận biết nhóm VN30TRI nhưng endpoint này không phải chuỗi close lịch sử. Không nội suy dữ liệu tháng, không khai thác giao thức biểu đồ riêng, và không thay VNINDEX giá thành total return. Chi tiết nguồn, URL và phần còn thiếu được ghi tại C2_source_feasibility.md và C2_source_audit.json.

Trạng thái C2: NOT_RUN_SOURCE_GATE_NOT_MET. Có 0 daily observation được chấp nhận; 641 ngày portfolio chưa thể đánh giá với chỉ số, không phải đã xác minh 641 ngày thị trường mất dữ liệu. Bảng C2 chỉ chứa trạng thái với ô metric trống; file daily chỉ có header. Không có biểu đồ so sánh ba đường hay kết luận vượt thị trường.

Để chạy tiếp cần daily level từ mốc 29/09/2023 đến 29/04/2026, index_date/index_level/vendor_record_date, phương pháp cổ tức/corporate actions, lịch thay đổi/vintage, thời điểm retrieval và xác nhận quyền nghiên cứu. Xin riêng quyền phát hành lại raw. Pipeline đã kiểm thử việc không nối return qua ngày thiếu và tính lại B1/B2 trên cùng mẫu liên tục ngắn hơn nếu cần. Chỉ số cổ phiếu vẫn khác tập khả thi của danh mục có VFF tối thiểu 30%; mọi so sánh sau này mang tính mô tả.

## 8. Kiểm chứng, giới hạn và nội dung xin ý kiến

Toàn bộ 310 target C1 thỏa ràng buộc; menu khớp B1/B2. Dựng lại NAV bằng số đơn vị tài sản độc lập cho sai số tối đa 8,66e-14. Identity traded notional = 2 × TO giữ đúng; các tests bao gồm mã vào/ra, execution-day jump, phí cấp vốn ban đầu/cuối kỳ, ví dụ metric tính tay và bootstrap ghép cặp. Kết quả test đầy đủ và hashes nằm trong validations.md và các manifest. Báo cáo không thay thế kiểm tra quyền dữ liệu hoặc chứng nhận giao dịch thực.

| So sánh | Câu hỏi được đánh giá | Giới hạn nhận diện |
| --- | --- | --- |
| C1–B1 | Quy tắc cố định so với phân bổ prior BL, cùng selector/menu | Không tách giá trị của selector; không kiểm định tương đương |
| C1–B2 | Quy tắc cố định so với toàn pipeline BL + ML | Không tách riêng đóng góp ML; cặp matched cho ML là B2–B1 |
| C2 chỉ số TR | Bối cảnh thị trường mô tả khi có nguồn hợp lệ | Khác lớp tài sản và ràng buộc; không suy ra alpha |

Các giới hạn còn nguyên: universe cố định 30 mã có survivorship risk; adjusted close là snapshot hồi cứu; publication vintage GOLD/VFF chưa xác minh hoàn chỉnh; GOLD/VFF là proxy định giá; chi phí chỉ là kịch bản; holdout đã quan sát. Không chỉnh sửa bằng chứng A+B để khắc phục các giới hạn này trong C.

Đề nghị giảng viên xem xét ba quyết định: (1) cập nhật diễn giải vai trò của prior BL trước đối chứng C1 gần B1; (2) quyết định nguồn/kinh phí/quyền truy cập VN30TRI để tiếp tục C2, hoặc chấp nhận feasibility stop; (3) chọn phạm vi C3/C4 nếu cần thêm kiểm định cơ chế. Không tái tối ưu B2 để bảo vệ kết quả cũ. C3–C6 có đề cương riêng trong optional_proposals.md và chưa được chạy.

Gói bằng chứng gồm source, snapshot mã C1, số liệu kết quả, biểu đồ, manifest/hash, tests và hướng dẫn tái chạy. Giá raw và lịch sử vendor giữ riêng ở inputs/ trên máy, không đưa vào Drive/ZIP khi chưa có quyền phân phối. Người tái chạy cần được cấp input pack hợp lệ; bộ kết quả công bố không tự nó cung cấp toàn bộ raw để chạy độc lập.

## 9. Tài liệu nguồn

Nguồn nội bộ: experiment_1.md (26/10/2026); protocol_frozen.md và baseline_manifest.json; bằng chứng Step 1/Step 2 theo hai run ID ở mục 2; toàn bộ kết quả C1 theo run ID đầu báo cáo. Tất cả bản dùng tính toán được nhận diện bằng SHA256.

Nguồn ngoài cho quyết định C2 (truy cập 04/11/2026): [1] HOSE, Factsheet market-cap indices 06/2026, staticfile.hsx.vn/Uploads/UploadDocuments/2468981/Form_Factsheet_MCIndices_VN_T06.2026.pdf. [2] HOSE index rules v1.2, SSC, dDocName APPSSCGOVVN162095654, mục 5A. [3] TradingView, HOSE-VN30TRI. [4] CEIC, Ho Chi Minh Stock Exchange Index: Total Return: VN30, monthly dataset. [5] FiinQuant, tài liệu hàm thống kê độ rộng thị trường. URL đầy đủ được giữ trong C2_source_feasibility.md để kiểm tra trực tiếp.
'''
    (HERE/'report_C_v1.md').write_text(report)
    print('Derived outputs and Vietnamese report generated',a.run)

if __name__=='__main__':main()
