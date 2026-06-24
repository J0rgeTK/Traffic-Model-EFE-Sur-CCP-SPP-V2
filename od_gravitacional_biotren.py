from __future__ import annotations
from pathlib import Path
import re, unicodedata, shutil, zipfile, json, math
import numpy as np
import pandas as pd

BASE_DIR=Path(__file__).resolve().parent
OD_MAIN=BASE_DIR/'data'/'od_biotren'/'input'/'0. Matrices Biotren may_2026.xlsx'
OD_MAR=BASE_DIR/'data'/'od_biotren'/'input'/'0. Matrices Biotren mar_2026.xlsx'
OD_ABR=BASE_DIR/'data'/'od_biotren'/'input'/'0. Matrices Biotren abr_2026.xlsx'
DIST_FILE=BASE_DIR/'data'/'od_biotren'/'input'/'Libro1.xlsx'
FARE_FILE=BASE_DIR/'data'/'od_biotren'/'input'/'Consolidado Tarifas EFE Sur 2026.xlsx'
MODEL=BASE_DIR
DATA=MODEL/'data'; OUT=MODEL/'outputs'; OD_DATA=DATA/'od_biotren'; OD_OUT=OUT/'od_biotren'
OD_DATA.mkdir(parents=True, exist_ok=True); OD_OUT.mkdir(parents=True, exist_ok=True)

MONTHS={'ene':1,'enero':1,'feb':2,'febrero':2,'mar':3,'marzo':3,'abr':4,'abril':4,'may':5,'mayo':5,'jun':6,'junio':6,'jul':7,'julio':7,'ago':8,'agos':8,'agosto':8,'sep':9,'sept':9,'septiembre':9,'oct':10,'octubre':10,'nov':11,'noviembre':11,'dic':12,'diciembre':12}

def strip_accents(s):
    s='' if s is None else str(s).strip()
    return ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))
def k(s):
    s=strip_accents(s).lower(); s=re.sub(r'[^a-z0-9]+',' ',s); return re.sub(r'\s+',' ',s).strip()
MAP={
 'hualqui':'Hualqui','la leonera':'La Leonera','leonera':'La Leonera','valle del sol':'La Leonera','manquimavida':'Manquimávida','pedro medina':'Pedro Medina','chiguayante':'Chiguayante','concepcion':'Concepción','mall':'Concepción Centro','concepcion centro':'Concepción Centro','lorenzo arenas':'Lorenzo Arenas','utfsm':'UTFSM','los condores':'Los Cóndores','higueras':'Higueras','arenal':'El Arenal','el arenal':'El Arenal','mercado':'Mercado','mercado de thno':'Mercado','juan pablo ii':'Juan Pablo II','diagonal biobio':'Diagonal Biobío','diagonal bio bio':'Diagonal Biobío','alborada':'Alborada','costa mar':'Costa Mar','el parque':'El Parque','megacentro':'El Parque','lomas coloradas':'Lomas Coloradas','raul silva h':'C. Raúl Silva H.','c raul silva h':'C. Raúl Silva H.','hito galvarino':'Hito Galvarino','los canelos':'Los Canelos','huinca':'Huinca','cristo redentor':'Cristo Redentor','laguna quinenco':'Laguna Quiñenco','lag quinenco':'Laguna Quiñenco','intermodal coronel':'Intermodal Coronel','coronel':'Intermodal Coronel','pasajero lota':'Pasajero Lota','lota':'Pasajero Lota','total':'Total','estaciones':'Estaciones'}
def canon(x): return MAP.get(k(x), str(x).strip() if x is not None else '')
def num(x):
    if pd.isna(x) or x=='': return 0.0
    if isinstance(x,(int,float,np.number)): return float(x)
    try: return float(str(x).replace('.','').replace(',','.'))
    except: return 0.0

def sheet_month(name):
    kk=k(name)
    if any(bad in kk for bad in ['resumen','hoja','supuesto','jun 2 0']): return None
    y=re.search(r'(20\d{2})',kk)
    if not y: return None
    for tok,m in MONTHS.items():
        if re.search(rf'\b{tok}\b',kk): return int(y.group(1)),m
    return None

def extract_block(df, block='Total Mes Tarjetas'):
    vals=df.values; target=k(block); pos=None
    for r in range(vals.shape[0]):
        for c in range(min(vals.shape[1],45)):
            if pd.notna(vals[r,c]) and target in k(vals[r,c]): pos=(r,c); break
        if pos: break
    if not pos: return None
    hr=sc=None
    for rr in range(pos[0]+1,min(pos[0]+7,vals.shape[0])):
        for cc in range(vals.shape[1]):
            if pd.notna(vals[rr,cc]) and k(vals[rr,cc])=='estaciones': hr=rr; sc=cc; break
        if hr is not None: break
    if hr is None: return None
    dest=[]; cols=[]
    for c in range(sc+1,vals.shape[1]):
        if pd.isna(vals[hr,c]): break
        cv=canon(vals[hr,c])
        if cv=='Total': break
        dest.append(cv); cols.append(c)
    rows=[]; origins=[]
    for r in range(hr+1,vals.shape[0]):
        if pd.isna(vals[r,sc]): continue
        ro=canon(vals[r,sc])
        if ro=='Total': break
        if ro in ['Estaciones','']: continue
        origins.append(ro); rows.append([num(vals[r,c]) for c in cols])
    if not rows: return None
    M=pd.DataFrame(rows,index=origins,columns=dest)
    M=M.groupby(level=0).sum(); M=M.T.groupby(level=0).sum().T
    common=[x for x in M.index if x in set(M.columns) and x not in ['Total','Estaciones']]
    M=M.loc[common,common]
    keep=[x for x in common if not (M.loc[x].sum()==0 and M[x].sum()==0)]
    return M.loc[keep,keep]

def load_od(path, blocks=('Total Mes Tarjetas',)):
    xls=pd.ExcelFile(path)
    mats={}; rec=[]
    for sh in xls.sheet_names:
        sm=sheet_month(sh)
        if not sm: continue
        df=pd.read_excel(path,sheet_name=sh,header=None,engine='openpyxl')
        for block in blocks:
            M=extract_block(df,block)
            if M is None: continue
            mats[(sm[0],sm[1],block)]=M
            rec.append({'archivo':path.name,'hoja':sh,'anio':sm[0],'mes':sm[1],'bloque':block,'n_origenes':M.shape[0],'n_destinos':M.shape[1],'total_viajes':M.to_numpy().sum()})
    return mats,pd.DataFrame(rec)

def read_matrix(path,sheet,hr,lc,fc,first_row=None,max_rows=None):
    df=pd.read_excel(path,sheet_name=sheet,header=None,engine='openpyxl'); vals=df.values
    hr-=1; lc-=1; fc-=1; first_row=(first_row or hr+2)-1
    heads=[]; cols=[]
    for c in range(fc,vals.shape[1]):
        if pd.isna(vals[hr,c]): break
        cv=canon(vals[hr,c])
        if cv=='Total': break
        heads.append(cv); cols.append(c)
    idx=[]; rows=[]; end=vals.shape[0] if max_rows is None else min(vals.shape[0], first_row+max_rows)
    for r in range(first_row,end):
        if pd.isna(vals[r,lc]): continue
        cv=canon(vals[r,lc])
        if cv=='Total': break
        if cv in ['Estaciones','']: continue
        idx.append(cv); rows.append([num(vals[r,c]) for c in cols])
    M=pd.DataFrame(rows,index=idx,columns=heads); M=M.groupby(level=0).mean(); M=M.T.groupby(level=0).mean().T
    return M

def ipf(seed, row, col, max_iter=100, tol=1e-7):
    M=np.maximum(np.array(seed,dtype=float),1e-12); row=np.array(row,dtype=float); col=np.array(col,dtype=float)
    if row.sum()<=0 or col.sum()<=0: return np.zeros_like(M),False,0,np.nan
    col=col*(row.sum()/col.sum())
    for it in range(max_iter):
        rs=M.sum(1); M=(M.T*np.where(rs>0,row/rs,0)).T
        cs=M.sum(0); M=M*np.where(cs>0,col/cs,0)
        if it%5==0:
            err=max(np.max(np.abs(M.sum(1)-row)/(row+1e-9)),np.max(np.abs(M.sum(0)-col)/(col+1e-9)))
            if err<tol: return M,True,it+1,err
    err=max(np.max(np.abs(M.sum(1)-row)/(row+1e-9)),np.max(np.abs(M.sum(0)-col)/(col+1e-9)))
    return M,False,max_iter,err

def imp(C,lam,kind):
    C=np.maximum(np.array(C,dtype=float),1e-6)
    return np.exp(-lam*C) if kind=='exponencial' else C**(-lam)
def met(obs,est):
    o=np.array(obs,dtype=float).ravel(); e=np.array(est,dtype=float).ravel(); er=e-o; ae=np.abs(er)
    m={'MAE':float(ae.mean()),'RMSE':float(np.sqrt(np.mean(er**2))),'MAPE_pct':float(np.nanmean(np.where(o>0,ae/o,np.nan))*100),'Correlacion':float(np.corrcoef(o,e)[0,1]) if np.std(o)>0 and np.std(e)>0 else np.nan,'Desviacion_abs_total':float(abs(e.sum()-o.sum())),'Desviacion_pct_total':float((e.sum()-o.sum())/(o.sum()+1e-9)*100),'CPC':float(2*np.minimum(o,e).sum()/(o.sum()+e.sum())) if o.sum()+e.sum()>0 else np.nan}
    ss=np.sum((o-o.mean())**2); m['R2']=float(1-np.sum(er**2)/ss) if ss>0 else np.nan
    return m
def cost(fare,dist,stations,a,b):
    F=fare.loc[stations,stations].astype(float); D=dist.loc[stations,stations].astype(float)
    Fn=F/F.replace(0,np.nan).stack().mean(); Dn=D/D.replace(0,np.nan).stack().mean(); C=a*Fn+b*Dn
    minpos=np.nanmin(C.to_numpy()[C.to_numpy()>0]); C=C.replace(0,minpos*.1)
    return C,Fn,Dn
def estimate(obs,C,lam,kind):
    seed=imp(C,lam,kind); np.fill_diagonal(seed,seed.diagonal()*0.05)
    M,conv,it,err=ipf(seed,obs.sum(1).to_numpy(),obs.sum(0).to_numpy())
    return pd.DataFrame(M,index=obs.index,columns=obs.columns),conv,it,err

def calibrate(mats,stations,fare,dist):
    keys=[x for x in mats if x[2]=='Total Mes Tarjetas']; train=[x for x in keys if x[0] in [2023,2024,2025]]; valid=[x for x in keys if x[0]==2026 and x[1] in [3,4,5]]
    agg=sum([mats[x].loc[stations,stations].astype(float) for x in train])
    rows=[]
    for a in [0.25,0.5,0.75]:
        C,_,_=cost(fare,dist,stations,a,1-a)
        for kind in ['exponencial','potencial']:
            for lam in [0.05,0.1,0.2,0.35,0.5,0.75,1,1.5,2,3]:
                est,_,_,_=estimate(agg,C,lam,kind); tm=met(agg,est)
                obs_all=[]; est_all=[]
                for vk in valid:
                    obs=mats[vk].loc[stations,stations].astype(float); ee,_,_,_=estimate(obs,C,lam,kind); obs_all.append(obs.to_numpy().ravel()); est_all.append(ee.to_numpy().ravel())
                vm=met(np.concatenate(obs_all),np.concatenate(est_all))
                row={'alpha':a,'beta':1-a,'funcion':kind,'lambda':lam,**{f'train_{kk}':vv for kk,vv in tm.items()},**{f'valid_{kk}':vv for kk,vv in vm.items()}}
                row['score']=row['valid_RMSE']*(1-0.15*max(row['valid_Correlacion'],0))*(1-0.1*max(row['valid_CPC'],0))
                rows.append(row)
    grid=pd.DataFrame(rows).sort_values(['score','valid_RMSE']).reset_index(drop=True); best=grid.iloc[0].to_dict(); C,Fn,Dn=cost(fare,dist,stations,best['alpha'],best['beta'])
    month_rows=[]
    for vk in valid:
        obs=mats[vk].loc[stations,stations].astype(float); ee,conv,it,err=estimate(obs,C,best['lambda'],best['funcion']); month_rows.append({'anio':vk[0],'mes':vk[1],'bloque':vk[2],**met(obs,ee),'converged':conv,'iteraciones':it,'error_balance':err})
    return best,grid,pd.DataFrame(month_rows),C,Fn,Dn,train,valid

def to_long(M,anio=None,mes=None,bloque=None,val='viajes'):
    df=M.stack().reset_index(); df.columns=['origen','destino',val]
    if anio is not None: df.insert(0,'anio',anio)
    if mes is not None: df.insert(1,'mes',mes)
    if bloque is not None: df.insert(2,'bloque',bloque)
    return df

