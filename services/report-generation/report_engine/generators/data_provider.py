import os
import json
import base64
import io
from datetime import datetime
from typing import Dict, Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def generate_svg_chart(chart_type: str, data: dict, labels: list, title: str, colors: list) -> str:
    """Generates a base64 encoded SVG string of a matplotlib chart, optimized for publication."""
    # Higher resolution, dashboard-like dimensions
    fig, ax = plt.subplots(figsize=(8.0, 4.5), dpi=300)
    
    # Common typography and styling constants
    font_main = 'sans-serif'
    color_text = '#15201a'
    color_muted = '#8a988f'
    color_grid = '#f4f6f3'
    
    plt.rcParams['font.family'] = font_main
    plt.rcParams['text.color'] = color_text
    plt.rcParams['axes.labelcolor'] = color_muted
    plt.rcParams['xtick.color'] = color_muted
    plt.rcParams['ytick.color'] = color_muted
    plt.rcParams['font.size'] = 11

    # Customize axes width and color globally
    plt.rcParams['axes.linewidth'] = 0

    if chart_type == 'bar':
        # Simplify stacked bar for matplotlib with rounded-like aesthetics
        bottom = [0] * len(labels)
        for i, (label, values) in enumerate(data.items()):
            # Rounded edges conceptually handled via slightly smaller width and high DPI
            bars = ax.bar(labels, values, label=label, bottom=bottom, color=colors[i % len(colors)], width=0.45, zorder=3, edgecolor='none')
            bottom = [b + v for b, v in zip(bottom, values)]
            
    elif chart_type == 'line':
        for i, (label, values) in enumerate(data.items()):
            # Smooth lines approximation and markers
            ax.plot(labels, values, label=label, color=colors[i % len(colors)], linewidth=3.5, marker='o', markersize=8, markerfacecolor='white', markeredgewidth=2.5, zorder=3)
            # Add a subtle area fill under the line to make it dashboard-like
            ax.fill_between(labels, 0, values, color=colors[i % len(colors)], alpha=0.05, zorder=2)
            
    elif chart_type == 'doughnut':
        values = list(data.values())
        if sum(values) == 0:
            values = [1] + [0]*(len(values)-1)
            colors = ['#f4f6f3'] + ['#ffffff']*(len(values)-1)
        
        # Donut chart with white borders for separation
        wedges, texts, autotexts = ax.pie(
            values, 
            labels=list(data.keys()), 
            colors=colors, 
            autopct='%1.0f%%',
            pctdistance=0.80,
            textprops={'fontsize': 11, 'color': color_text, 'weight': '600'},
            wedgeprops=dict(width=0.4, edgecolor='white', linewidth=3)
        )
        for t in texts:
            t.set_fontsize(11)
            t.set_color(color_muted)
        
    ax.set_title(title, color=color_text, fontsize=16, fontweight='800', pad=25, loc='left')
    
    if chart_type != 'doughnut':
        # Clean up axes
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        
        ax.tick_params(colors=color_muted, labelsize=10, length=0, pad=10)
        # Add horizontal grid lines behind the data
        ax.yaxis.grid(True, color=color_grid, linestyle='-', linewidth=1.5, zorder=0)
        ax.xaxis.grid(False)
        
        # Add a subtle background to the legend
        leg = ax.legend(loc='upper right', bbox_to_anchor=(1.0, 1.15), ncol=3, frameon=False, fontsize=10, handlelength=1.0, handletextpad=0.8)
        for text in leg.get_texts():
            text.set_color(color_muted)

    plt.tight_layout()
    
    buf = io.BytesIO()
    # Save as high-quality SVG
    plt.savefig(buf, format='svg', transparent=True, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def get_filtered_data(year: int, month: str, compare: str, config) -> Dict[str, Any]:
    import csv
    
    data = {}
    def ensure_year(y_str):
        if y_str not in data:
            data[y_str] = {
                'label': f"{y_str} Data", 'frequency': 'annual', 'population': None,
                'petrolL': [None]*12, 'trDieselL': [None]*12, 'dgL': [None]*12,
                'htKwh': [None]*12, 'commKwh': [None]*12, 'tempKwh': [None]*12,
                'reKwh': [None]*12, 'avoidEm': [None]*12,
                'petrolEm': [None]*12, 'trDieselEm': [None]*12, 'dgEm': [None]*12,
                'htEm': [None]*12, 'commEm': [None]*12, 'tempEm': [None]*12,
            }
        return data[y_str]

    months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    month_idx = {m.lower(): i for i, m in enumerate(months)}

    def m_idx(m_str):
        if not m_str: return None
        k = str(m_str).strip()[:3].lower()
        return month_idx.get(k)

    def add_val(arr, i, val):
        if i is not None and val is not None:
            if arr[i] is None: arr[i] = 0
            arr[i] += val

    def num(v):
        if v is None or str(v).strip() == '' or str(v).lower() == 'null': return None
        try: return float(str(v).replace(',', ''))
        except ValueError: return None

    EF = {'petrol': 2.388, 'diesel': 2.701, 'grid': 0.727}
    
    data_dir = config.DASHBOARD_DATA_DIR
    
    # Load EF
    try:
        with open(os.path.join(data_dir, 'emission_factors.csv'), 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                k = str(row.get('factor_key', '')).lower()
                v = num(row.get('emission_factor'))
                if k and v is not None: EF[k] = v
    except FileNotFoundError: pass

    # Load transport
    try:
        with open(os.path.join(data_dir, 'transport_master.csv'), 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                y = str(row.get('year', '')).strip()
                if not y: continue
                i = m_idx(row.get('month'))
                fuel = str(row.get('fuel_type', '')).lower()
                qty = num(row.get('consumption_litre'))
                if 'petrol' in fuel: add_val(ensure_year(y)['petrolL'], i, qty)
                elif 'diesel' in fuel: add_val(ensure_year(y)['trDieselL'], i, qty)
    except FileNotFoundError: pass

    # Load dg
    try:
        with open(os.path.join(data_dir, 'dg_master.csv'), 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                y = str(row.get('year', '')).strip()
                if not y: continue
                add_val(ensure_year(y)['dgL'], m_idx(row.get('month')), num(row.get('consumption_litre')))
    except FileNotFoundError: pass

    # Load electricity
    try:
        with open(os.path.join(data_dir, 'electricity_master.csv'), 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                y = str(row.get('year', '')).strip()
                if not y: continue
                i = m_idx(row.get('month'))
                typ = str(row.get('connection_type', '')).lower()
                qty = num(row.get('consumption_kwh'))
                d = ensure_year(y)
                if 'ht' in typ: add_val(d['htKwh'], i, qty)
                elif 'commercial' in typ: add_val(d['commKwh'], i, qty)
                elif 'temporary' in typ: add_val(d['tempKwh'], i, qty)
    except FileNotFoundError: pass

    # Load RE
    try:
        with open(os.path.join(data_dir, 'renewable_master.csv'), 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                y = str(row.get('year', '')).strip()
                qty = num(row.get('renewable_kwh'))
                if not y or qty is None: continue
                d = ensure_year(y)
                m = str(row.get('month', '')).strip().lower()
                i = m_idx(m)
                if i is not None:
                    add_val(d['reKwh'], i, qty)
                else:
                    count = 4 if 'ytd' in m or d['frequency'] == 'ytd' else 12
                    d['frequency'] = 'ytd' if count == 4 else d['frequency']
                    for k in range(count): add_val(d['reKwh'], k, qty/count)
    except FileNotFoundError: pass

    # Load dashboard JSON overlay
    output_file = os.path.join(config.OUTPUT_DIR, "dashboard_master.json")
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            master = json.load(f)
            api_data = master.get("data", {})
            for rec in api_data.get('energy', []):
                y, m = rec.get('Year'), rec.get('Month')
                if not y or not m: continue
                d, i = ensure_year(str(y)), m_idx(m)
                if i is None: continue
                if rec.get('Industrial') is not None: d['htKwh'][i] = rec['Industrial']
                if rec.get('Commercial') is not None: d['commKwh'][i] = rec['Commercial']
                if rec.get('Temporary') is not None: d['tempKwh'][i] = rec['Temporary']
                if rec.get('Total_RE') is not None: d['reKwh'][i] = rec['Total_RE']
            for rec in api_data.get('transport', []):
                y, m = rec.get('Year'), rec.get('Month')
                if not y or not m: continue
                d, i = ensure_year(str(y)), m_idx(m)
                if i is None: continue
                if rec.get('Petrol_Litres') is not None: d['petrolL'][i] = rec['Petrol_Litres']
                if rec.get('Diesel_Litres') is not None: d['trDieselL'][i] = rec['Diesel_Litres']

    if str(year) not in data:
        # We'll just create it to avoid crashing if year isn't found
        ensure_year(str(year))
        
    year_data = data[str(year)]
    
    def safe_n(val):
        try: return float(val) if val is not None else 0.0
        except (ValueError, TypeError): return 0.0
            
    def sum_arr(arr, end=12):
        if not arr: return 0.0
        return sum(safe_n(x) for x in arr[:end])

    def get_val(arr, m, freq):
        if not arr: return 0.0
        if m == 'all':
            end = 4 if freq == 'ytd' else 12
            return sum_arr(arr, end)
        try:
            return safe_n(arr[int(m)])
        except (IndexError, ValueError):
            return 0.0
            
    for y_key, d in data.items():
        # Calculate Emissions using Emission Factors
        d['htEm'] = [safe_n(d.get('htKwh', [])[i] if i < len(d.get('htKwh', [])) else 0) * EF.get('grid', 0.727) / 1000 for i in range(12)]
        d['commEm'] = [safe_n(d.get('commKwh', [])[i] if i < len(d.get('commKwh', [])) else 0) * EF.get('grid', 0.727) / 1000 for i in range(12)]
        d['tempEm'] = [safe_n(d.get('tempKwh', [])[i] if i < len(d.get('tempKwh', [])) else 0) * EF.get('grid', 0.727) / 1000 for i in range(12)]
        
        d['petrolEm'] = [safe_n(d.get('petrolL', [])[i] if i < len(d.get('petrolL', [])) else 0) * EF.get('petrol', 2.388) / 1000 for i in range(12)]
        d['trDieselEm'] = [safe_n(d.get('trDieselL', [])[i] if i < len(d.get('trDieselL', [])) else 0) * EF.get('diesel', 2.701) / 1000 for i in range(12)]
        d['dgEm'] = [safe_n(d.get('dgL', [])[i] if i < len(d.get('dgL', [])) else 0) * EF.get('diesel', 2.701) / 1000 for i in range(12)]
        
        d['avoidEm'] = [safe_n(d.get('reKwh', [])[i] if i < len(d.get('reKwh', [])) else 0) * EF.get('grid', 0.727) / 1000 for i in range(12)]

        d['elecKwh'] = [safe_n(d.get('htKwh', [])[i] if i < len(d.get('htKwh', [])) else 0) +
                        safe_n(d.get('commKwh', [])[i] if i < len(d.get('commKwh', [])) else 0) +
                        safe_n(d.get('tempKwh', [])[i] if i < len(d.get('tempKwh', [])) else 0)
                        for i in range(12)]
        
        d['elecEm'] = [safe_n(d.get('htEm', [])[i] if i < len(d.get('htEm', [])) else 0) +
                       safe_n(d.get('commEm', [])[i] if i < len(d.get('commEm', [])) else 0) +
                       safe_n(d.get('tempEm', [])[i] if i < len(d.get('tempEm', [])) else 0)
                       for i in range(12)]
                       
        d['scope1Selected'] = [safe_n(d.get('petrolEm', [])[i] if i < len(d.get('petrolEm', [])) else 0) +
                               safe_n(d.get('trDieselEm', [])[i] if i < len(d.get('trDieselEm', [])) else 0) +
                               safe_n(d.get('dgEm', [])[i] if i < len(d.get('dgEm', [])) else 0)
                               for i in range(12)]
                               
        d['dieselCombo'] = [safe_n(d.get('trDieselEm', [])[i] if i < len(d.get('trDieselEm', [])) else 0) +
                            safe_n(d.get('dgEm', [])[i] if i < len(d.get('dgEm', [])) else 0)
                            for i in range(12)]
                            
        d['grossSelected'] = [d['scope1Selected'][i] + d['elecEm'][i] for i in range(12)]
        
        end = 4 if d.get('frequency') == 'ytd' else 12
        d['totalGHG'] = sum_arr(d['grossSelected'], end)
        
        if d.get('population'):
            d['perCapita'] = d['totalGHG'] / float(d['population'])
        else:
            d['perCapita'] = 0.0

    d = year_data
    freq = d.get('frequency', 'annual')
    
    scope1 = get_val(d.get('scope1Selected', []), month, freq)
    diesel = get_val(d.get('dieselCombo', []), month, freq)
    petrol = get_val(d.get('petrolEm', []), month, freq)
    scope2 = get_val(d.get('elecEm', []), month, freq)
    elec = get_val(d.get('elecKwh', []), month, freq)
    re = get_val(d.get('reKwh', []), month, freq)
    avoid = get_val(d.get('avoidEm', []), month, freq)
    gross = scope1 + scope2
    net = gross - avoid
    
    def get_prev_value(arr_name):
        if compare == 'mom' and month != 'all':
            pm = int(month) - 1
            if pm >= 0:
                return get_val(d.get(arr_name, []), str(pm), freq)
        py = data.get(str(year - 1))
        if not py:
            return None
        if compare == 'ytd' or month == 'all':
            end = 4 if d.get('frequency') == 'ytd' else 12
            return sum_arr(py.get(arr_name, []), end)
        return get_val(py.get(arr_name, []), month, freq)

    prev_gross = get_prev_value('grossSelected')
    prev_elec = get_prev_value('elecKwh')
    prev_re = get_prev_value('reKwh')
    prev_avoid = get_prev_value('avoidEm')
    prev_scope1 = get_prev_value('scope1Selected')
    prev_scope2 = get_prev_value('elecEm')
    
    def get_trend(cur, prev, lower_good=True):
        if prev is None or prev == 0:
            return {"trend_pct": 0, "good": True, "label": "no comparison", "raw": 0}
        p = ((cur - prev) / prev) * 100
        good = p <= 0 if lower_good else p >= 0
        return {"trend_pct": round(abs(p), 1), "good": good, "raw": p}

    report_title = f"{months[int(month)]} {year}" if month != 'all' else f"{year}"
    report_label = d.get('label', report_title)

    # Generate SVGs
    chart_colors = {
        'emerald': '#1c7a4b', 'lime': '#5aa552', 'cyan': '#3a6fa8', 'blue': '#3a6fa8', 
        'teal': '#4f9a8c', 'gold': '#c18a2e', 'orange': '#b8623a', 'red': '#be4b3b'
    }
    
    def sl(arr):
        if not arr: return [0]*12
        return [(v if v is not None else 0) for v in arr[:12]]

    s1_diesel_svg = generate_svg_chart('line', {
        'Transport diesel': sl(d.get('trDieselEm')),
        'DG diesel': sl(d.get('dgEm'))
    }, months, 'Scope 1 - Fuel Emissions', [chart_colors['gold'], chart_colors['orange']])

    s1_breakdown_svg = generate_svg_chart('doughnut', {
        'Transport diesel': sum(sl(d.get('trDieselEm'))),
        'DG diesel': sum(sl(d.get('dgEm'))),
        'Petrol': sum(sl(d.get('petrolEm')))
    }, [], 'Scope 1 Breakdown', [chart_colors['gold'], chart_colors['orange'], chart_colors['teal']])

    s2_stack_svg = generate_svg_chart('bar', {
        'HT': sl(d.get('htKwh')),
        'Commercial': sl(d.get('commKwh')),
        'Temporary': sl(d.get('tempKwh'))
    }, months, 'Scope 2 - Grid Consumption', [chart_colors['cyan'], '#6e97c7', chart_colors['teal']])

    re_mix_svg = generate_svg_chart('doughnut', {
        'Renewable energy': d.get('reEnergy', sum(sl(d.get('reKwh')))),
        'Grid electricity': d.get('gridEnergy', sum(sl(d.get('elecKwh'))))
    }, [], 'Renewable Mix', [chart_colors['emerald'], chart_colors['blue']])

    charts = {
        's1_diesel': s1_diesel_svg,
        's1_breakdown': s1_breakdown_svg,
        's2_stack': s2_stack_svg,
        're_mix': re_mix_svg
    }

    # Generate Insights
    def generate_insights():
        insights = {}
        
        # Scope 1 / Transport Insight
        s1_trend = get_trend(scope1, prev_scope1)
        prev_petrol = get_prev_value('petrolEm') or 0
        prev_diesel = get_prev_value('trDieselEm') or 0
        transport_trend = get_trend(petrol + get_val(d.get('trDieselEm', []), month, freq), prev_petrol + prev_diesel)
        
        if transport_trend['raw'] > 0:
            primary_cause = "Diesel fleet usage" if get_val(d.get('trDieselEm', []), month, freq) > petrol else "Petrol vehicle usage"
            insights['transport'] = f"Transport emissions increased {transport_trend['trend_pct']}%. Primary cause: {primary_cause}. Suggested improvement: Electrify campus buses."
        else:
            insights['transport'] = f"Transport emissions decreased by {transport_trend['trend_pct']}%. Continued fleet optimization is contributing to this reduction."
            
        s1_major = "Diesel Generators" if sum(sl(d.get('dgEm'))) > sum(sl(d.get('trDieselEm'))) + sum(sl(d.get('petrolEm'))) else "Transport"
        insights['scope1'] = f"Scope 1 emissions generated {scope1:.2f} tCO₂e. {s1_major} remains the dominant emission source in this category. Overall Scope 1 emissions {'increased' if s1_trend['raw'] > 0 else 'decreased'} by {s1_trend['trend_pct']}% compared to the previous period."
        
        # Scope 2 Insight
        s2_trend = get_trend(scope2, prev_scope2)
        insights['scope2'] = f"Grid electricity consumption accounted for {scope2:.2f} tCO₂e. This represents {((scope2/gross)*100) if gross else 0:.1f}% of total gross emissions. Scope 2 emissions {'rose' if s2_trend['raw'] > 0 else 'fell'} by {s2_trend['trend_pct']}%. Continuous efforts in optimizing HVAC and lighting can further reduce this footprint."
        
        # Renewable Insight
        re_share = (re/(re+elec)*100) if (re+elec) else 0
        insights['renewable'] = f"Renewable energy integration contributed {re:.2f} kWh, offsetting approximately {avoid:.2f} tCO₂e of potential emissions. Our current renewable share stands at {re_share:.1f}%."
        
        # Executive Summary
        if gross > 0:
            insights['executive'] = f"During this reporting period, the campus generated {gross:.2f} tCO₂e of gross carbon emissions. Through our renewable energy initiatives, we successfully avoided {avoid:.2f} tCO₂e, resulting in a net carbon impact of {net:.2f} tCO₂e. We remain committed to our long-term decarbonization pathway."
        else:
            insights['executive'] = "Data for the current reporting period is still being aggregated. Please ensure all utility inputs have been approved by verifiers."
            
        insights['recommendations'] = [
            "Accelerate the transition of internal campus mobility to Electric Vehicles (EVs) to reduce Scope 1 transport emissions.",
            "Expand rooftop solar capacity to push the renewable energy mix beyond the current baseline.",
            "Implement automated BMS (Building Management Systems) for high-load commercial blocks to optimize HVAC consumption."
        ]
        
        return insights

    return {
        "year": year,
        "month": month,
        "report_title": f"Carbon Emissions Report - {report_title}",
        "report_label": report_label,
        "compare": compare,
        "generation_date": datetime.now().strftime("%d %B %Y"),
        "kpis": {
            "gross": {"value": gross, "trend": get_trend(gross, prev_gross, True)},
            "elec": {"value": elec, "trend": get_trend(elec, prev_elec, True)},
            "re": {"value": re, "trend": get_trend(re, prev_re, False)},
            "avoid": {"value": avoid, "trend": get_trend(avoid, prev_avoid, False)},
            "scope1": {"value": scope1, "trend": get_trend(scope1, prev_scope1, True)},
            "scope2": {"value": scope2, "trend": get_trend(scope2, prev_scope2, True)},
            "net": {"value": net},
            "perCapita": {"value": d.get('perCapita', 0)},
            "petrolL": {"value": get_val(d.get('petrolL', []), month, freq)},
            "petrolEm": {"value": petrol},
            "trDieselL": {"value": get_val(d.get('trDieselL', []), month, freq)},
            "trDieselEm": {"value": get_val(d.get('trDieselEm', []), month, freq)},
            "dgL": {"value": get_val(d.get('dgL', []), month, freq)},
            "dgEm": {"value": get_val(d.get('dgEm', []), month, freq)},
            "dieselCombo": {"value": diesel},
            "gridEF": {"value": 0.727},
            "elecContrib": {"value": (scope2 / gross * 100) if gross else 0},
            "scope2Offset": {"value": (avoid / scope2 * 100) if scope2 else 0},
            "reShare": {"value": d.get('reShare', (re/(re+elec)*100) if (re+elec) else 0)}
        },
        "charts": charts,
        "current_period": d,
        "current_month_index": month,
        "months": months,
        "insights": generate_insights()
    }
