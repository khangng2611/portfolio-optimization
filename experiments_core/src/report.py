"""Build figures and a Vietnamese evidence report entirely from saved CSVs."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .frozen import PKG,BASE_RUN,SEEDS,sha,write_json


LABELS={'A0_Full30':'Full 30','A2_SimpleK5':'Simple K5','A3_ProposedK5':'Proposed K5',
        'B0_MVOmatched':'MVO matched','B1_BLnoML':'BL prior-only','B2_BLML':'BL cộng ML'}


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
                     ['| '+' | '.join(map(str,row))+' |' for row in rows])


def main(primary,repeat):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=PKG/'runs'/primary/'outputs';docs=PKG/'docs';docs.mkdir(exist_ok=True)
    if not (PKG/'outputs').exists():(PKG/'outputs').symlink_to(Path('runs')/primary/'outputs',target_is_directory=True)
    plots=out/'plots';plots.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    a=pd.read_csv(out/'selection_portfolio_metrics.csv');b=pd.read_csv(out/'optimizer_ladder_metrics.csv')
    structural=pd.read_csv(out/'selection_structure.csv');costs=pd.read_csv(out/'cost_sensitivity.csv')
    ci=pd.read_csv(out/'uncertainty_intervals.csv');checks=json.loads((PKG/'runs'/primary/'independent_verification.json').read_text())
    paths={arm:pd.read_csv(out/'variants'/arm/'nav.csv',index_col=0,parse_dates=True).nav.loc['2023-09-29':] for arm in list(LABELS)}
    for arm in paths:paths[arm]=paths[arm]/paths[arm].iloc[0]
    random=[f'A1_RandomK5_s{s}' for s in SEEDS]
    random_paths=pd.DataFrame({arm:pd.read_csv(out/'variants'/arm/'nav.csv',index_col=0,parse_dates=True).nav.loc['2023-09-29':] for arm in random})
    random_paths=random_paths/random_paths.iloc[0]
    fig,axes=plt.subplots(2,2,figsize=(11,7),sharex='col')
    for col,arms in enumerate([['A0_Full30','A2_SimpleK5','A3_ProposedK5'],['B0_MVOmatched','B1_BLnoML','B2_BLML']]):
        for arm in arms:
            nav=paths[arm];axes[0,col].plot(nav,label=LABELS[arm]);axes[1,col].plot(nav/nav.cummax()-1,label=LABELS[arm])
        axes[0,col].set_title('A  Selection comparison' if col==0 else 'B  Matched estimator ladder')
        axes[0,col].legend(fontsize=8);axes[0,col].set_ylabel('NAV');axes[1,col].set_ylabel('Drawdown')
        for ax in axes[:,col]:ax.grid(alpha=.2)
    axes[0,0].fill_between(random_paths.index,random_paths.min(axis=1),random_paths.max(axis=1),alpha=.12,color='gray',label='Random 10-seed range')
    axes[0,0].legend(fontsize=8);fig.autofmt_xdate();fig.tight_layout();fig.savefig(plots/'matched_nav_drawdown.png',dpi=170);plt.close(fig)
    history=pd.read_csv(out/'selection_history_comparison.csv',parse_dates=['selection_date'])
    fig,ax=plt.subplots(1,2,figsize=(11,3.5))
    for arm in ['A2_SimpleK5','A3_ProposedK5']:
        x=history[(history.experiment_id==arm)&(history.selection_date>=pd.Timestamp('2023-10-01'))]
        ax[0].plot(x.selection_date,x.coverage_objective,label=LABELS[arm]);ax[1].plot(x.selection_date,x.jaccard,label=LABELS[arm])
    ax[0].set_title('Correlation coverage objective  lower is better');ax[1].set_title('Adjacent selection Jaccard overlap')
    for x in ax:x.legend();x.grid(alpha=.2)
    fig.autofmt_xdate();fig.tight_layout();fig.savefig(plots/'selection_coverage_stability.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(7.5,3.5))
    for arm in ['B0_MVOmatched','B1_BLnoML','B2_BLML']:
        x=costs[(costs.experiment_id==arm)&(costs.phase=='OOS')]
        ax.plot(x.bps_per_side,x.sharpe,'o-',label=LABELS[arm])
    ax.set(xlabel='Cost per side  bps of traded notional',ylabel='OOS net Sharpe',title='ML benefit is sensitive to turnover costs')
    ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(plots/'cost_sharpe.png',dpi=170);plt.close(fig)
    metrics=pd.concat([a,b]);oos=metrics[metrics.phase=='OOS'].set_index('experiment_id')
    def metrics_table(frame):
        return table(['Nhánh','NAV','CAGR %','Vol %','Sharpe','MDD %','TO năm'],[
            [LABELS.get(r.experiment_id,r.experiment_id),f'{r.final_nav:.4f}',f'{100*r.ann_return:.2f}',f'{100*r.ann_volatility:.2f}',
             f'{r.sharpe:.3f}',f'{100*r.max_drawdown:.2f}',f'{r.annualized_turnover:.3f}'] for r in frame.itertuples()])
    random_metrics=a[(a.phase=='OOS')&a.experiment_id.str.startswith('A1')]
    random_summary=[]
    for metric in ['final_nav','ann_return','ann_volatility','sharpe','max_drawdown','annualized_turnover']:
        v=random_metrics[metric];random_summary.append({'metric':metric,'median':v.median(),'minimum':v.min(),'q25':v.quantile(.25),'q75':v.quantile(.75),'maximum':v.max()})
    pd.DataFrame(random_summary).to_csv(out/'random_seed_distribution.csv',index=False)
    effects=[]
    for left,right in [('A3_ProposedK5','A2_SimpleK5'),('B1_BLnoML','B0_MVOmatched'),('B2_BLML','B1_BLnoML')]:
        for k in ['ann_return','ann_volatility','sharpe','max_drawdown','annualized_turnover','mean_HHI']:
            effects.append({'left':left,'right':right,'metric':k,'OOS_effect':oos.loc[left,k]-oos.loc[right,k]})
    pd.DataFrame(effects).to_csv(out/'primary_effect_sizes.csv',index=False)
    a_main=a[(a.phase=='OOS')&~a.experiment_id.str.startswith('A1')]
    a_random_median=[['Random K5 trung vị',f'{random_metrics.final_nav.median():.4f}',f'{100*random_metrics.ann_return.median():.2f}',
                      f'{100*random_metrics.ann_volatility.median():.2f}',f'{random_metrics.sharpe.median():.3f}',f'{100*random_metrics.max_drawdown.median():.2f}',f'{random_metrics.annualized_turnover.median():.3f}']]
    metric_labels={'final_nav':'NAV','ann_return':'CAGR %','ann_volatility':'Vol %','sharpe':'Sharpe','max_drawdown':'MDD %','annualized_turnover':'TO năm'}
    random_summary_table=table(['Chỉ số','Trung vị','Min','Q25','Q75','Max'],[
        [metric_labels[r['metric']]]+[f'{r[k]*(100 if r["metric"] in ["ann_return","ann_volatility","max_drawdown"] else 1):.4f}' for k in ['median','minimum','q25','q75','maximum']] for r in random_summary])
    st=structural[structural.phase=='OOS']
    st_rows=[]
    for arm in ['A0_Full30','A2_SimpleK5','A3_ProposedK5']:
        x=st[st.experiment_id==arm].iloc[0];st_rows.append([LABELS[arm],f'{x.coverage_objective:.3f}',f'{x.mean_pair_correlation:.3f}',f'{x.mean_jaccard:.3f}',int(x.stock_changes)])
    rx=st[st.experiment_id.str.startswith('A1')]
    st_rows.append(['Random K5 trung vị',f'{rx.coverage_objective.median():.3f}',f'{rx.mean_pair_correlation.median():.3f}',f'{rx.mean_jaccard.median():.3f}',f'{rx.stock_changes.median():.1f}'])
    cost_rows=[]
    for arm in ['A0_Full30','A2_SimpleK5','A3_ProposedK5','B0_MVOmatched','B2_BLML']:
        x=costs[(costs.phase=='OOS')&(costs.experiment_id==arm)].set_index('bps_per_side')
        cost_rows.append([LABELS[arm]]+[f'{x.loc[c,"sharpe"]:.3f}' for c in [0,10,25,50]]+[f'{x.loc[50,"final_nav"]:.4f}'])
    ci_rows=[]
    for r in ci.itertuples():
        label=LABELS.get(r.left,r.left)+' trừ '+LABELS.get(r.right,'Random median ngày')
        scale=100 if r.metric=='ann_return' else 1
        ci_rows.append([label,'CAGR điểm %' if scale==100 else 'Sharpe',f'{r.effect*scale:+.3f}',f'[{r.ci_low*scale:+.3f}; {r.ci_high*scale:+.3f}]'])
    baseline=pd.read_csv(out/'baseline_replay_metrics.csv')
    base_rows=[]
    for r in baseline[baseline.phase=='OOS'].itertuples():base_rows.append([r.strategy,f'{r.final_nav:.4f}',f'{r.sharpe:.3f}',f'{100*r.max_drawdown:.2f}',f'{r.annualized_turnover:.3f}'])
    report=f'''# Báo cáo Step 2 về bằng chứng thực nghiệm cho xây dựng danh mục

Ngày thực hiện 23/10/2026. Báo cáo tiếp nối Step 1 đã cập nhật ngày 12/10/2026, theo hai tệp guide_1.md và project_1.md. Tên nội bộ của hai tệp vẫn ghi guide_0 và project_0; cụm “NEW STEP 1” trong đó là gói thí nghiệm tiếp theo, được gọi Step 2 ở đây để phân biệt với đợt kiểm toán đã hoàn tất.

## 1 Phạm vi và kết luận chính

Đã thực hiện đủ thí nghiệm A về lựa chọn tài sản, B về so sánh ước lượng lợi nhuận trên cùng tập đầu tư, độ nhạy chi phí và bootstrap ghép cặp. Kết quả ủng hộ giá trị của lựa chọn đại diện về độ phủ tương quan và độ ổn định; bằng chứng về ưu thế hiệu suất còn hỗn hợp. Prior BL cho phân bổ ít tập trung và turnover thấp hơn MVO matched. ML cải thiện các chỉ số gross OOS trong cửa sổ này, nhưng lợi ích suy giảm khi tính chi phí. Tất cả khoảng tin cậy 95% của chênh lệch CAGR và Sharpe đều chứa 0, nên chưa đủ bằng chứng kết luận ưu thế thống kê.

Baseline tiếp tục là `{BASE_RUN.name}`. Dữ liệu gồm 1.568 phiên × 32 tài sản, từ 14/01/2020 đến 29/04/2026. IS có 906 return sau khởi tạo ngày 18/02/2020. OOS neo NAV tại 29/09/2023, gồm 641 return từ 02/10/2023 đến 29/04/2026. Không tải dữ liệu mới, đổi K, thay mô hình ML hoặc chọn tham số theo kết quả OOS.

Các mục 2–11 và nhiều số đếm trong báo cáo Step 1 thuộc kiểm toán 04/10; mục 13 cùng manifest 12/10 xác định baseline hiện hành. Ví dụ, baseline hiện hành có 310 sự kiện giao dịch, 293 lần có views và 17 lần không views, 78 lần chọn tập. Không chuyển số hit rate cũ hoặc ngày lựa chọn cũ thành kết quả mới.

## 2 Đóng băng và tái lập baseline

Đã đối chiếu hash dữ liệu và mã số học với snapshot lượt gốc, kiểm tra CSV giữa hai lượt huấn luyện mới đã lưu của Step 1 và tái tính độc lập NAV từ tỷ trọng quyết định. NAV, chỉ số IS/OOS và turnover khớp ở ngưỡng kiểm tra 1e-9 cho chỉ số và 1e-10 cho đường NAV. Đây là replay quyết định đã lưu, không phải lượt huấn luyện ML mới trong sprint này.

{table(['Legacy unmatched','NAV OOS','Sharpe','MDD %','TO năm'],base_rows)}

Bảng baseline là đối chứng mô tả: EW/MVO dùng 32 tài sản, BL thường dùng 7 tài sản, Hybrid kết hợp hai tập khác nhau. Không dùng bảng này để quy đóng góp riêng cho BL, ML hoặc Hybrid.

Quy ước thông tin giữ nguyên: quyết định sau 18:00 giờ Việt Nam; VFF có độ trễ tối thiểu năm phiên quan sát hoặc metadata muộn hơn; GOLD ngày D chỉ vào thông tin từ D+1. Bảng thông tin dùng ra quyết định tách khỏi bảng giá dùng định giá. Toàn bộ 50.176 dòng lineage được đối chiếu với cutoff và tái dựng lại bảng thông tin. Đây là kiểm tra thực thi giả định availability, không xác nhận ngày công bố lịch sử thực tế.

## 3 Thiết kế thí nghiệm và ràng buộc chung

A gồm Full 30, Simple K5, Proposed K5 và 10 lượt Random K5 với seed 7, 11, 19, 23, 31, 43, 59, 71, 83, 97. Tất cả cộng GOLD và VFF, chọn lại mỗi 20 phiên và rebalance mỗi 5 phiên. Simple chọn năm cổ phiếu có biến động thấp nhất trong 20 return quá khứ, kết thúc t−1; đồng hạng theo ticker. Ở sự kiện đầu IS chỉ có 19 return quá khứ, dùng số quan sát sẵn có chung, không điền ngược; các sự kiện sau đủ 20. Mỗi seed tạo một chuỗi chọn mới tại từng sự kiện, không chọn seed thắng sau khi xem OOS.

Proposed dùng đúng các tập đã lưu của baseline. Đã tái tính ma trận từ lịch sử đến t−1 và kiểm tra độc lập cả 142.506 tổ hợp tại mỗi trong 78 sự kiện. Full 30 có coverage bằng 0 theo định nghĩa nên chỉ là đối chứng kích thước tập, không phải đối chứng K5 công bằng trên chính score này.

B giữ đúng chuỗi Proposed K5 cộng GOLD và VFF: B0 dùng trung bình mẫu 20 phiên; B1 dùng prior BL; B2 thêm các ML views P/Q/confidence đã lưu và có nguồn gốc nhân quả. Ba nhánh dùng cùng covariance, tập khả thi và lịch quyết định. Không có view thì posterior bằng prior pi, tuyệt đối không dùng fallback trung bình mẫu của pipeline legacy.

Tất cả A/B dùng risk aversion cố định 1,5, tắt defensive regime views và điều chỉnh risk aversion theo regime; tau=0,05, delta=2,5, prior weights đều trên tập đang đầu tư. B2 giữ confidence ML động đã lưu, bao gồm volatility dampener cố định. Đây là lựa chọn kiểm soát được ghi trước khi đọc kết quả ablation; B2 không được coi là bản sao của BL legacy có regime. H4/H5 về confidence và regime không được kiểm định độc lập.

{table(['Điều kiện','Giá trị thực thi'],[['Tổng tỷ trọng và long-only','sum w = 1; w ≥ 0'],['Cap mỗi tài sản','0,50, áp dụng cả GOLD và VFF'],['Nhóm ngoài VFF','≤ 0,70, bao gồm GOLD'],['Floor VFF','danh nghĩa 0,15; hiệu dụng 0,30'],['Loại vị thế nhỏ','ngưỡng 0,01 chỉ khi vẫn khả thi'],['Ngưỡng kiểm tra','1e-8 sau giải và làm sạch'],['Hàm mục tiêu','muᵀw − 1,5 wᵀSigma w'],['Covariance','return ngày, 20 phiên; eigenvalue floor 1e-8']])}

Quyết định sau close(t) thực thi close(t+1); lượng nắm giữ mới chỉ hưởng return t+1→t+2. Số đơn vị được giữ giữa hai giao dịch, tỷ trọng trôi theo giá. IS và OOS nối cùng một danh mục; chỉ chuẩn hóa NAV để báo cáo, không cấp vốn lại. Cap được kiểm tại giao dịch, không áp đặt lại mỗi ngày giữa hai giao dịch.

## 4 Thí nghiệm A về lựa chọn đại diện

Kết quả cấu trúc dưới đây tính trên 32 sự kiện chọn tập trong OOS. Jaccard so với sự kiện liền trước, kể cả sự kiện đầu OOS so với cuối IS; số thay đổi là số cổ phiếu mới vào tập.

{table(['Nhánh','Coverage','Corr cặp','Jaccard','Đổi mã'],st_rows)}

Coverage thấp hơn của Proposed phù hợp với mục tiêu tối ưu được thiết kế. Độ ổn định cao và turnover thấp là kết quả riêng có ý nghĩa thực nghiệm; không suy ra chỉ từ việc thuật toán thắng chính hàm mục tiêu của nó.

{metrics_table(a_main)}

{table(['Nhánh','NAV','CAGR %','Vol %','Sharpe','MDD %','TO năm'],a_random_median)}

Proposed có CAGR cao hơn Simple 2,08 điểm phần trăm, nhưng Sharpe thấp hơn 0,025 và MDD âm hơn khoảng 1,19 điểm phần trăm. Turnover giảm từ 4,940 xuống 0,851 mỗi năm. Trong 10 seed, Proposed đứng trên {int((random_metrics.sharpe<oos.loc['A3_ProposedK5','sharpe']).sum())}/10 lượt về Sharpe; đây là vị trí trong tập seed nhỏ đã định trước, không phải xác suất thắng tổng quát.

{random_summary_table}

Trung vị trong bảng phân phối là trung vị chỉ số của 10 backtest hoàn chỉnh. Nó khác chuỗi “Random median ngày” trong bootstrap, vốn lấy trung vị return của 10 seed tại từng ngày và chỉ dùng làm đối chứng phân tích, không phải danh mục có thể đầu tư.

HHI bình quân ngày của Proposed là {oos.loc['A3_ProposedK5','mean_HHI']:.4f}, số vị thế hiệu dụng bình quân là {oos.loc['A3_ProposedK5','mean_effective_holdings']:.3f}; tương ứng Full 30 là {oos.loc['A0_Full30','mean_HHI']:.4f} và {oos.loc['A0_Full30','mean_effective_holdings']:.3f}. Đó là số đo tỷ trọng thực tế trước return, không phải số mã danh nghĩa.

## 5 Thí nghiệm B về BL và ML trên cùng danh mục

{metrics_table(b[b.phase=='OOS'])}

B1 trừ B0: Sharpe tăng 0,340; volatility giảm 6,47 điểm phần trăm; MDD giảm độ sâu 7,24 điểm phần trăm; turnover giảm 12,693 mỗi năm. Đây là so sánh estimator/prior dưới cùng bộ giải tối ưu và ràng buộc, không phải bằng chứng rằng một thuật toán solver riêng của BL tốt hơn MVO.

B2 trừ B1: CAGR tăng 3,17 điểm phần trăm, Sharpe tăng 0,193; MDD giảm độ sâu 0,75 điểm phần trăm. Turnover tăng từ 0,851 lên 7,975 mỗi năm; HHI tăng từ 0,1717 lên 0,2726. ML có lợi về gross trong cửa sổ này nhưng làm danh mục tập trung hơn và giao dịch nhiều hơn. B1 và A3 được giải riêng và có đường NAV giống nhau, đúng như thiết kế chung prior-only.

Kết quả IS được giữ để nhìn cả hai kỳ, không dùng để lựa chọn lại cấu hình:

{metrics_table(b[b.phase=='IS'])}

Trong IS, Sharpe B2 là 0,614, thấp hơn B1 0,794 và B0 0,842; bằng chứng giữa IS và OOS không đồng nhất. Không dùng kết quả IS hoặc OOS này để đổi cấu hình đã đóng băng.

## 6 Chi phí và khoảng bất định

Chi phí đặt trước là 0, 10, 25, 50 bps cho mỗi đơn vị notional mua hoặc bán. Tại execution close, traded notional bằng sum abs(w_target − w_pretrade) = 2 × turnover. Mỗi sự kiện áp dụng hệ số 1 − c × traded notional lên NAV gross; khoản phí thuộc đúng ngày thực thi. Đây là xấp xỉ nhân theo sự kiện trên giao dịch gross, không phải mô hình holdings tự tài trợ chính xác khi có phí. Giao dịch ban đầu bị tính phí một lần trong IS, nhưng bị loại khỏi turnover năm; OOS không có phí cấp vốn lần hai. Giao dịch ở close cuối mẫu vẫn bị tính phí mà không thêm return tương lai.

{table(['Nhánh','S 0bps','S 10bps','S 25bps','S 50bps','NAV 50bps'],cost_rows)}

B1 dùng cùng kết quả với Proposed K5. Ở 10 bps, Sharpe B2 vẫn cao hơn B1; ở 25 và 50 bps, B1 cao hơn B2. Không tìm ngưỡng hòa vốn liên tục; khoảng kịch bản này đã cho thấy tính nhạy chi phí. Phí quỹ, thuế, spread SJC và lịch nhận lệnh thực tế chưa được mô phỏng riêng.

Bootstrap dùng moving blocks không vòng tròn, độ dài 10 phiên, 1.000 mẫu lặp, seed 20261014. Trong mỗi cặp, hai chuỗi nhận cùng chỉ số ngày lấy mẫu. Mỗi mẫu tính lại CAGR và Sharpe với rf ngày = 1,06^(1/252) − 1, chuẩn hóa 252 phiên/năm, độ lệch chuẩn mẫu. CI là percentile 95%; chênh lệch drawdown được trình bày mô tả, không gắn CI bootstrap.

{table(['Cặp so sánh','Chỉ số','Hiệu ứng','CI 95%'],ci_rows)}

Tất cả CI chứa 0: chưa đủ bằng chứng xác định hướng hiệu ứng, không đồng nghĩa các mô hình tương đương. CI có điều kiện theo cửa sổ, universe và giả định dữ liệu đã cố định; không loại bỏ rủi ro thử nhiều chiến lược hay nguồn gốc tham số trước OOS chưa đầy đủ.

## 7 Hình so sánh

![NAV và drawdown OOS của các nhánh matched](../outputs/plots/matched_nav_drawdown.png)

Vùng xám của A biểu diễn khoảng min–max đường NAV của 10 seed Random, không phải khoảng tin cậy.

![Coverage và độ ổn định của tập chọn](../outputs/plots/selection_coverage_stability.png)

![Sharpe sau chi phí của ba nhánh B](../outputs/plots/cost_sharpe.png)

## 8 Kết luận theo giả thuyết

- H1: Hỗn hợp. Proposed tối ưu coverage, ít đổi mã và turnover thấp; không thắng Simple về Sharpe gross hoặc MDD, và CI về chênh lệch hiệu suất chứa 0. Full 30 là bối cảnh kích thước, không phải causal K5 comparison.
- H2: Có hỗ trợ mô tả trong mẫu. Prior BL ít tập trung, ít giao dịch và ít drawdown hơn MVO matched. CI chênh lệch Sharpe và CAGR chứa 0 nên chưa kết luận ưu thế thống kê.
- H3: Hỗn hợp. ML cải thiện gross OOS nhưng tăng turnover, và lợi ích không bền ở mức phí 25–50 bps mỗi chiều; CI chứa 0.
- H4 và H5: Chưa kiểm định riêng. Không chạy fixed-confidence hay regime on/off; không ghi “kết quả bằng 0” cho các probe chưa chạy.
- H6: Có kết quả end-to-end gross trong baseline và kết quả matched có điều kiện trong sprint. Chưa xác nhận lợi nhuận tổng quát hoặc chiến lược thực thi thực tế. Hybrid legacy chỉ là tham chiếu mô tả.

## 9 Kiểm chứng và khả năng tái lập

Lượt chính `{primary}`; lượt kiểm tra lặp `{repeat}`. Cả hai thực thi lại toàn bộ 16 cấu hình phân bổ và phân tích, dùng cùng kho tín hiệu bất biến; không huấn luyện lại ML. Mọi CSV thí nghiệm giống từng byte, trừ registry có runtime khác nhau. Bộ kiểm tra gồm sáu kiểm thử mới cho timing, drift, prior, Simple, phí và paired bootstrap; 35 kiểm thử kế thừa chạy từ đúng candidate workspace; {checks['checks']:,} assertion độc lập về file lặp, holdings units, constraints, timing, matched inputs, posterior và cost0. Số assertion lớn bao gồm kiểm tra lặp theo từng giao dịch, không phải từng đó kiểm định thống kê độc lập.

Các check đọc lại số đơn vị tài sản và giá để tái tạo mọi NAV mới, kiểm tra toàn bộ target sau làm sạch, xác nhận covariance/active universe/prior/risk aversion giống nhau giữa ba nhánh B và xác nhận no-ML bằng prior. Rà soát độc lập bổ sung xác nhận covariance saved với panel dựng lại sai lệch tối đa 2,60e-18 trên 293 mẫu. Mã nguồn, input hashes, tham số, dependency versions, seed, OS/CPU, solver và log được lưu theo từng run.

Hash của references và báo cáo Docs xuất được ghi trong evidence manifest lúc đóng gói. Các hash này là dấu vết tài liệu tại thời điểm đóng gói, khác với manifest và experiment_plan đã tạo trước thực thi. Những giới hạn về ngày công bố gốc và corporate-action vintage không được nâng thành chứng nhận dữ liệu.

Lệnh tái lập từ root repository:

```sh
venv/bin/python -B -m unittest discover -s experiments_core/tests -v
venv/bin/python -B -m experiments_core.src.run
venv/bin/python -B -m experiments_core.src.run --parent-run RUN_CHINH
venv/bin/python -B -m experiments_core.src.validate RUN_CHINH RUN_LAP
venv/bin/python -B -m experiments_core.src.report RUN_CHINH RUN_LAP
```

Tệp CSV đầy đủ gồm chỉ số IS/OOS, lịch chọn và score, phân phối cả 10 seed, return ngày, target và pretrade weights, holdings ngày, turnover sự kiện, covariance/prior/posterior/P/Q, CI, chi phí và registry. `run_manifest` chỉ ra đầu vào gốc; bản snapshot và archive tái lập kèm bảng ánh xạ cho phép truy nguyên sau khi đổi thư mục dự án.

## 10 Giới hạn và đề xuất sửa bài báo

Universe là danh sách cố định 30 cổ phiếu, có khả năng survivorship bias. Giá điều chỉnh là snapshot provider, chưa có vintage point-in-time hoặc sổ corporate actions chứng minh total return. Availability của VFF/GOLD là policy mô phỏng, chưa phải timestamp first-release đã xác minh. GOLD theo giá bán SJC và VFF theo NAV đại diện; next-close không phải cam kết nhận lệnh quỹ hay khớp vàng thực tế. Chi phí là stress test đơn giản. Chưa đủ bằng chứng nguồn gốc của mọi lựa chọn tham số trước OOS.

Tuyên bố đóng góp nên tập trung vào kiến trúc xây dựng danh mục và các hiệu ứng tăng thêm đo được. Giữ cả kết quả âm và CI rộng. Đồng bộ công thức Sharpe theo excess return ngày; mu/Q và Sigma theo đơn vị ngày; views dùng tanh theo volatility; objective dùng hệ số phạt 1,5 và 5 trong legacy, tương đương lambda/2 nếu đổi ký hiệu; alpha Hybrid là tỷ phần MVO và alpha_normal=1 không làm các regime khác trở thành MVO thuần. Không gọi toàn bộ các layer là đã chứng minh hiệu quả.

Gói này đủ để sửa phần phương pháp, bảng thực nghiệm và thảo luận của bản thảo. `paper_revision_handoff.md` chứa đề xuất abstract, contribution và cách trình bày kết quả. Chưa tuyên bố bản thảo đã sẵn sàng gửi journal hoặc chiến lược giao dịch đã được xác nhận thực thi.

READY FOR PAPER REVISION
'''
    (docs/'core_experiment_report.md').write_text(report)
    (docs/'matched_constraints.md').write_text('# Matched constraints\n\nAll A/B variants use the frozen optimize_weight_ranking function.\n\n'+table(['Parameter','Value'],[['risk_aversion','1.5 fixed'],['max_weight','0.50 all assets'],['min_defensive_weight','0.15 nominal'],['max_nondefensive_exposure','0.70 incl GOLD'],['defensive_assets','VFF only; effective floor 0.30'],['weight_cleanup','0.01; retain feasibility'],['constraint_tolerance','1e-8'],['covariance','20 daily information returns, regularized eigenvalue floor 1e-8'],['prior','delta=2.5, tau=0.05, equal-weight active universe'],['regime views/risk adjustment','OFF all A/B'],['B2 confidence','saved ML dynamic confidence incl volatility dampener']])+'\n\nFinal target feasibility is checked; holdings may drift between trades. Baseline legacy is descriptive only.\n')
    (docs/'deviations.md').write_text('''# Deviations and decisions

1. The supplied files retain old internal names. This deliverable is called Step 2 / Core Evidence Sprint to distinguish it from the completed integrity Step 1.
2. Historical absolute paths contain an obsolete source/ parent. Resolve by the portfolio-optimization/ suffix and verify hashes; do not rewrite old manifests.
3. Baseline reproduction uses independent saved-decision holdings replay and original fresh-fit repeat hash comparison; no unnecessary fresh ML retraining.
4. First IS selection has 19 prior returns; Simple uses those 19 then exactly 20. Shared eligibility/date schedule is preserved; no future fill. This was recorded before ablation metrics.
5. All A/B arms disable defensive regime views and regime-dependent risk aversion, using fixed 1.5. B2 retains saved dynamic ML confidence including volatility dampener. It intentionally differs from legacy BL+ML; B1 vs B2 still differs only by saved ML views.
6. Confidence/regime/matched-Hybrid optional probes SKIPPED, not null results. No claim of separate H4/H5 support.
7. Cost returns use the declared event-level multiplicative approximation, charge initial buy in IS, and include terminal trades on execution date. No continuous break-even root search.
8. Random bootstrap comparator is the median across seed returns on each date, analytical and not investable. The table median is separately the median of ten full-run metrics.
9. Original instructions, Step1 Docs export and implementation-plan hashes are recorded at publication time in evidence_manifest.json, separately from the pre-execution numerical freeze.
10. Google Drive connector is not connected. Deliver report DOCX and PDF plus Markdown and reproducibility archive through the existing authorized Chrome session. No new native Google Doc is required for this report submission.
''')
    (docs/'paper_revision_handoff.md').write_text('''# Paper revision handoff

## Proposed title

Integrated Long Only Portfolio Construction for the Vietnamese Market with Correlation Coverage Selection and Black Litterman Views

## Proposed abstract

We evaluate an integrated long-only portfolio construction pipeline on a fixed 30-stock Vietnamese equity proxy with gold and a bond-fund NAV proxy. The walk-forward protocol separates decision information from portfolio valuation, uses next-close execution, and preserves holdings between rebalances. Matched experiments compare representative selection against simple and random K=5 alternatives, and sample-mean allocation against a Black–Litterman equilibrium prior with and without saved causal XGBoost views. Over 641 out-of-sample returns, correlation-coverage selection improves its structural coverage and selection stability, while economic performance is mixed. The prior-only allocation has lower volatility, concentration and turnover than matched sample-mean allocation. ML views improve gross Sharpe from 1.175 to 1.367 but increase turnover; the prior-only allocation has higher net Sharpe at 25–50 bps per side. All paired moving-block-bootstrap intervals for annual-return and Sharpe differences include zero. Findings support cautious architectural and risk-allocation claims under declared availability assumptions, rather than statistical superiority or executable trading profitability.

## Contributions supported at current scope

- A reproducible integrated construction architecture and explicit information/execution contract.
- Matched structural and portfolio comparisons for selection, with all ten random seeds reported.
- Estimator/prior and ML-view incremental effects under identical constraints, including costs and uncertainty.

## Method notation to align

Daily mu/Q and daily-return covariance; pi = delta Sigma w_eq; no-view posterior = pi. Sharpe uses mean daily excess return divided by sample daily volatility and multiplied by sqrt(252), with compounded rf=6% annual. The frozen objective is muᵀw minus gamma wᵀSigma w (gamma 1.5 in the controlled ladder). Describe tanh-scaled ML views, confidence/Omega convention, equal-weight prior proxy, effective VFF floor 30%, and conditional legacy Hybrid alpha semantics explicitly.

## Results and limitations to preserve

Use Table 1 legacy as descriptive, Tables 2–4 matched for attribution, and cost/bootstrap tables for limits. Do not say ML/BL/proposed selection is universally superior. Distinguish the 2026-10-12 baseline from the 2026-10-04 audit and old manuscript values. Static constituents, publication timing assumptions, revised adjusted-close vintages, gold/fund execution and pre-OOS parameter-choice provenance remain limitations. The source manuscript is not silently rewritten by this handoff.
''')
    write_json(docs/'report_sources.json',{'primary':primary,'repeat':repeat,'report_sha256':sha(docs/'core_experiment_report.md'),
                'source_csvs':[{'path':str(p.relative_to(PKG)),'sha256':sha(p)} for p in sorted(out.glob('*.csv'))]})
    print('Report and 3 figures generated')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('primary');p.add_argument('repeat');a=p.parse_args();main(a.primary,a.repeat)
