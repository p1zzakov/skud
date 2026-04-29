import { useState, useEffect, useRef, useCallback } from "react";

const fmt     = iso => iso ? new Date(iso).toLocaleString("ru-RU") : "—";
const fmtTime = iso => iso ? new Date(iso).toLocaleTimeString("ru-RU") : "—";
const fmtDate = iso => iso ? new Date(iso).toLocaleDateString("ru-RU") : "—";

const api = {
  get:  url        => fetch(url).then(r=>r.json()),
  post: (url,body) => fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(r=>r.json()),
  put:  (url,body) => fetch(url,{method:"PUT", headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(r=>r.json()),
  del:  url        => fetch(url,{method:"DELETE"}).then(r=>r.json()),
};

const Badge = ({children,color="gray"})=>{
  const c={green:"bg-green-100 text-green-800",red:"bg-red-100 text-red-800",
    blue:"bg-blue-100 text-blue-800",gray:"bg-gray-100 text-gray-600",
    yellow:"bg-yellow-100 text-yellow-800",purple:"bg-purple-100 text-purple-800"};
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${c[color]||c.gray}`}>{children}</span>;
};

const Btn = ({children,onClick,color="blue",size="md",className=""})=>{
  const colors={blue:"bg-blue-600 hover:bg-blue-700 text-white",
    green:"bg-green-600 hover:bg-green-700 text-white",
    red:"bg-red-50 hover:bg-red-100 text-red-700",
    gray:"bg-slate-100 hover:bg-slate-200 text-slate-700"};
  const sizes={md:"px-4 py-2 text-sm",sm:"px-3 py-1.5 text-xs",lg:"px-6 py-3 text-base"};
  return <button onClick={onClick}
    className={`${colors[color]||colors.blue} ${sizes[size]||sizes.md} rounded-lg font-medium transition-colors ${className}`}>
    {children}
  </button>;
};

const Input = ({label,value,onChange,type="text",placeholder=""})=>(
  <div>
    {label && <label className="block text-sm font-medium text-slate-600 mb-1">{label}</label>}
    <input type={type} value={value||""} onChange={e=>onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
  </div>
);

const Select = ({label,value,onChange,options,placeholder="Выберите..."})=>(
  <div>
    {label && <label className="block text-sm font-medium text-slate-600 mb-1">{label}</label>}
    <select value={value||""} onChange={e=>onChange(e.target.value)}
      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none">
      <option value="">{placeholder}</option>
      {options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </div>
);

const Modal = ({title,onClose,children,footer})=>(
  <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
      <div className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0">
        <h3 className="text-lg font-bold text-slate-800">{title}</h3>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl">✕</button>
      </div>
      <div className="overflow-auto flex-1 px-6 py-4 space-y-4">{children}</div>
      {footer && <div className="px-6 py-4 border-t flex gap-3 justify-end flex-shrink-0">{footer}</div>}
    </div>
  </div>
);

const Avatar = ({photo,name,size=10})=>{
  const sz = `w-${size} h-${size}`;
  return photo
    ? <img src={photo} alt={name} className={`${sz} rounded-full object-cover border border-slate-200 flex-shrink-0`}
           onError={e=>e.target.style.display='none'}/>
    : <div className={`${sz} rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-bold flex-shrink-0`}>
        {(name||"?").charAt(0)}
      </div>;
};

function Login({onLogin}){
  const [u,setU]=useState("admin");
  const [p,setP]=useState("");
  const [err,setErr]=useState("");
  const submit=async e=>{
    e.preventDefault();
    const r=await api.post("/api/auth/login",{username:u,password:p});
    if(r.ok) onLogin(r); else setErr("Неверный логин или пароль");
  };
  return(
    <div className="min-h-screen bg-gradient-to-br from-slate-800 to-slate-900 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-2xl p-10 w-96">
        <div className="text-center mb-8">
          <div className="text-4xl mb-3">🔐</div>
          <h1 className="text-2xl font-bold text-slate-800">СКУД КЕЛЕТ</h1>
          <p className="text-slate-500 text-sm mt-1">Система контроля доступа</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <Input value={u} onChange={setU} placeholder="Логин"/>
          <Input type="password" value={p} onChange={setP} placeholder="Пароль"/>
          {err && <p className="text-red-500 text-sm">{err}</p>}
          <button className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-3 font-semibold transition-colors">Войти</button>
        </form>
      </div>
    </div>
  );
}

function Monitor(){
  const [events,setEvents]=useState([]);
  const [stats,setStats]=useState({});
  const [filter,setFilter]=useState({dir:"",search:""});

  const load=useCallback(async()=>{
    const [ev,st]=await Promise.all([api.get("/api/events?limit=100"),api.get("/api/stats")]);
    setEvents(ev.events||[]); setStats(st);
  },[]);

  useEffect(()=>{
    load();
    const proto=location.protocol==="https:"?"wss":"ws";
    const ws=new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage=e=>{
      const msg=JSON.parse(e.data);
      if(msg.type==="event"){
        setEvents(prev=>[msg.data,...prev].slice(0,200));
        setStats(prev=>({...prev,today_events:(prev.today_events||0)+1}));
      }
    };
    ws.onclose=()=>setTimeout(load,3000);
    return()=>ws.close();
  },[load]);

  const filtered=events.filter(ev=>{
    if(filter.dir && ev.direction!==filter.dir) return false;
    if(filter.search && !ev.employee_name?.toLowerCase().includes(filter.search.toLowerCase())) return false;
    return true;
  });

  const dirColor=d=>d==="in"?"green":d==="out"?"red":"gray";
  const dirLabel=d=>d==="in"?"↓ Вход":d==="out"?"↑ Выход":d;

  return(
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[
          {label:"Сотрудников",value:stats.employees},
          {label:"Событий сегодня",value:stats.today_events},
          {label:"Контроллеров онлайн",value:`${stats.controllers_online||0}/${stats.controllers_total||0}`},
          {label:"Последнее событие",value:events[0]?fmtTime(events[0].server_time):"—"},
        ].map(s=>(
          <div key={s.label} className="bg-white rounded-xl p-4 shadow-sm border border-slate-100">
            <p className="text-slate-500 text-xs uppercase tracking-wide">{s.label}</p>
            <p className="text-2xl font-bold text-slate-800 mt-1">{s.value??0}</p>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-xl shadow-sm border border-slate-100">
        <div className="flex items-center gap-4 px-6 py-4 border-b flex-wrap">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"/>
            <span className="font-semibold text-slate-800">Live мониторинг</span>
          </div>
          <input placeholder="Поиск по имени..." value={filter.search}
            onChange={e=>setFilter(p=>({...p,search:e.target.value}))}
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none flex-1 max-w-xs"/>
          <select value={filter.dir} onChange={e=>setFilter(p=>({...p,dir:e.target.value}))}
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none">
            <option value="">Все направления</option>
            <option value="in">Вход</option>
            <option value="out">Выход</option>
          </select>
          <span className="text-slate-400 text-sm ml-auto">{filtered.length} событий</span>
        </div>
        <div className="divide-y divide-slate-50 max-h-[600px] overflow-auto">
          {filtered.length===0&&<div className="text-center text-slate-400 py-16">Ожидание событий...</div>}
          {filtered.map((ev,i)=>(
            <div key={ev.id||i} className="flex items-center gap-3 px-6 py-3 hover:bg-slate-50 transition-colors">
              <Badge color={dirColor(ev.direction)}>{dirLabel(ev.direction)}</Badge>
              {ev.employee_id&&<Avatar photo={`/photos/${ev.employee_id}.jpg`} name={ev.employee_name} size={9}/>}
              <div className="flex-1 min-w-0">
                <p className="font-medium text-slate-800 truncate">{ev.employee_name||"Неизвестная карта"}</p>
                <p className="text-xs text-slate-400 truncate">
                  {ev.department}{ev.department&&" • "}{ev.controller_name||ev.controller_ip} • {ev.card_hex}
                </p>
              </div>
              <span className="text-slate-400 text-sm whitespace-nowrap">{fmtTime(ev.server_time)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Employees(){
  const [list,setList]=useState([]);
  const [search,setSearch]=useState("");
  const [deptId,setDeptId]=useState("");
  const [depts,setDepts]=useState([]);
  const [modal,setModal]=useState(null);
  const [form,setForm]=useState({});
  const [cards,setCards]=useState([]);
  const [newCard,setNewCard]=useState("");
  const [scanning,setScanning]=useState(false);

  const load=useCallback(async()=>{
    const p=new URLSearchParams();
    if(search) p.set("search",search);
    if(deptId) p.set("department_id",deptId);
    const [emps,deps]=await Promise.all([api.get(`/api/employees?${p}`),api.get("/api/departments")]);
    setList(emps); setDepts(deps);
  },[search,deptId]);

  useEffect(()=>{load();},[load]);

  const openEdit=async emp=>{
    setModal(emp); setForm({...emp});
    const c=await api.get(`/api/cards?employee_id=${emp.id}`);
    setCards(c);
  };
  const openNew=()=>{
    setModal("new");
    setForm({full_name:"",tab_number:"",department_id:"",position:"",phone:"",email:""});
    setCards([]);
  };

  const save=async()=>{
    const body={...form,department_id:form.department_id?Number(form.department_id):null};
    if(modal==="new") await api.post("/api/employees",body);
    else await api.put(`/api/employees/${modal.id}`,body);
    setModal(null); load();
  };

  const deactivate=async id=>{
    if(!confirm("Деактивировать сотрудника?")) return;
    await api.del(`/api/employees/${id}`); load();
  };

  const refreshCards=async()=>{
    if(modal&&modal!=="new"){
      const c=await api.get(`/api/cards?employee_id=${modal.id}`);
      setCards(c);
    }
  };

  const addCard=async()=>{
    if(!newCard.trim()) return;
    const r=await api.post("/api/cards",{card_hex:newCard.trim(),employee_id:modal.id});
    if(r.ok){ setNewCard(""); refreshCards(); }
    else alert("Ошибка: карта уже существует");
  };

  const removeCard=async id=>{ await api.del(`/api/cards/${id}`); refreshCards(); };

  const scanCard=()=>{
    setScanning(true);
    const proto=location.protocol==="https:"?"wss":"ws";
    const ws=new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage=e=>{
      const msg=JSON.parse(e.data);
      if(msg.type==="event"){ setNewCard(msg.data.card_hex); setScanning(false); ws.close(); }
    };
    setTimeout(()=>{ setScanning(false); ws.close(); },15000);
  };

  const deptOptions=depts.map(d=>({value:d.id,label:`${d.company_name||""} / ${d.city_name||""} / ${d.name}`}));

  return(
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-slate-800">Сотрудники</h2>
        <Btn onClick={openNew}>+ Добавить</Btn>
      </div>
      <div className="flex gap-3 mb-4">
        <input placeholder="Поиск по имени или табному" value={search}
          onChange={e=>setSearch(e.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
        <select value={deptId} onChange={e=>setDeptId(e.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none">
          <option value="">Все подразделения</option>
          {depts.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 uppercase text-xs">
            <tr>
              <th className="px-4 py-3 text-left">Фото</th>
              <th className="px-4 py-3 text-left">ФИО</th>
              <th className="px-4 py-3 text-left">Табельный</th>
              <th className="px-4 py-3 text-left">Подразделение</th>
              <th className="px-4 py-3 text-left">Должность</th>
              <th className="px-4 py-3 text-left">Карты</th>
              <th className="px-4 py-3"/>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {list.map(emp=>(
              <tr key={emp.id} className="hover:bg-slate-50">
                <td className="px-4 py-2"><Avatar photo={emp.photo} name={emp.full_name} size={10}/></td>
                <td className="px-4 py-3 font-medium text-slate-800">{emp.full_name}</td>
                <td className="px-4 py-3 text-slate-500">{emp.tab_number||"—"}</td>
                <td className="px-4 py-3 text-slate-600">{emp.dept_name||emp.department||"—"}</td>
                <td className="px-4 py-3 text-slate-500">{emp.position||"—"}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {emp.cards
                      ?emp.cards.split(",").map(c=><Badge key={c} color="blue">{c}</Badge>)
                      :<span className="text-slate-400 text-xs">нет</span>}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 justify-end">
                    <button onClick={()=>openEdit(emp)} className="text-blue-500 hover:text-blue-700 text-sm">✏️</button>
                    <button onClick={()=>deactivate(emp.id)} className="text-red-400 hover:text-red-600 text-sm">🗑</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.length===0&&<div className="text-center text-slate-400 py-10">Нет сотрудников</div>}
      </div>

      {modal&&(
        <Modal title={modal==="new"?"Новый сотрудник":form.full_name}
          onClose={()=>setModal(null)}
          footer={<><Btn color="gray" onClick={()=>setModal(null)}>Отмена</Btn><Btn onClick={save}>Сохранить</Btn></>}>
          {modal!=="new"&&(
            <div className="flex justify-center"><Avatar photo={modal.photo} name={modal.full_name} size={20}/></div>
          )}
          <Input label="ФИО" value={form.full_name} onChange={v=>setForm(p=>({...p,full_name:v}))}/>
          <Input label="Табельный номер" value={form.tab_number} onChange={v=>setForm(p=>({...p,tab_number:v}))}/>
          <Select label="Подразделение" value={form.department_id}
            onChange={v=>setForm(p=>({...p,department_id:v}))}
            options={deptOptions} placeholder="Выберите подразделение"/>
          <Input label="Должность" value={form.position} onChange={v=>setForm(p=>({...p,position:v}))}/>
          <Input label="Телефон" value={form.phone} onChange={v=>setForm(p=>({...p,phone:v}))}/>
          <Input label="Email" type="email" value={form.email} onChange={v=>setForm(p=>({...p,email:v}))}/>

          {modal!=="new"&&(
            <div>
              <label className="block text-sm font-medium text-slate-600 mb-2">Карты доступа</label>
              <div className="space-y-2 mb-3 max-h-40 overflow-auto">
                {cards.map(c=>(
                  <div key={c.id} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2">
                    <span className="font-mono text-sm">{c.card_hex}</span>
                    <button onClick={()=>removeCard(c.id)} className="text-red-400 hover:text-red-600 text-xs">✕</button>
                  </div>
                ))}
                {cards.length===0&&<p className="text-slate-400 text-sm">Нет карт</p>}
              </div>
              <div className="flex gap-2">
                <input className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Hex карты (напр. 7350BE)"
                  value={newCard} onChange={e=>setNewCard(e.target.value)}/>
                <Btn onClick={addCard} size="sm">Добавить</Btn>
                <button onClick={scanCard}
                  className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors
                    ${scanning?"border-orange-400 text-orange-600 animate-pulse bg-orange-50"
                    :"border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
                  {scanning?"⏳ Приложите...":"📡 Сканировать"}
                </button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}

function Controllers(){
  const [list,setList]=useState([]);
  const [cities,setCities]=useState([]);
  const [modal,setModal]=useState(null);
  const [form,setForm]=useState({});

  const load=async()=>{
    const [c,ci]=await Promise.all([api.get("/api/controllers"),api.get("/api/cities")]);
    setList(c); setCities(ci);
  };
  useEffect(()=>{load();const t=setInterval(load,5000);return()=>clearInterval(t);},[]);

  const openEdit=c=>{setModal(c);setForm({name:c.name||"",location:c.location||"",city_id:c.city_id||""});};
  const save=async()=>{
    await api.put(`/api/controllers/${modal.id}`,{...form,city_id:form.city_id?Number(form.city_id):null});
    setModal(null); load();
  };
  const sendCmd=async(ip,action)=>await api.post(`/api/controllers/${ip}/command`,{action});
  const cityOptions=cities.map(c=>({value:c.id,label:`${c.company_name} / ${c.name}`}));

  return(
    <div>
      <h2 className="text-xl font-bold text-slate-800 mb-6">Контроллеры</h2>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {list.map(c=>(
          <div key={c.ip} className="bg-white rounded-xl shadow-sm border border-slate-100 p-5">
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${c.online?"bg-green-500 animate-pulse":"bg-red-400"}`}/>
                  <h3 className="font-semibold text-slate-800 truncate">{c.name||c.ip}</h3>
                </div>
                <p className="text-sm text-slate-500 mt-0.5">{c.ip} • {c.mac||"—"}</p>
                {c.location&&<p className="text-xs text-slate-400">{c.location}</p>}
                {c.city_name&&<p className="text-xs text-slate-400">{c.company_name} / {c.city_name}</p>}
              </div>
              <div className="flex flex-col items-end gap-1 flex-shrink-0">
                <Badge color={c.online?"green":"red"}>{c.online?"Онлайн":"Оффлайн"}</Badge>
                <button onClick={()=>openEdit(c)} className="text-blue-500 hover:text-blue-700 text-xs">⚙️ Настроить</button>
              </div>
            </div>
            <div className="text-xs text-slate-500 mb-3 flex gap-3">
              <span>Режим: <strong>{c.mode}</strong></span>
              <span>Считывателей: {c.num_readers}</span>
            </div>
            {c.online&&(
              <div className="flex gap-2">
                <button onClick={()=>sendCmd(c.ip,"open")}
                  className="flex-1 bg-green-50 hover:bg-green-100 text-green-700 rounded-lg py-2 text-sm font-medium">🔓 Открыть</button>
                <button onClick={()=>sendCmd(c.ip,"close")}
                  className="flex-1 bg-red-50 hover:bg-red-100 text-red-700 rounded-lg py-2 text-sm font-medium">🔒 Закрыть</button>
              </div>
            )}
            <p className="text-xs text-slate-400 mt-2">Последний пакет: {c.last_seen?fmtTime(c.last_seen):"—"}</p>
          </div>
        ))}
        {list.length===0&&<div className="col-span-3 bg-white rounded-xl p-16 text-center text-slate-400">Контроллеры не обнаружены</div>}
      </div>

      {modal&&(
        <Modal title={`Настройка: ${modal.ip}`} onClose={()=>setModal(null)}
          footer={<><Btn color="gray" onClick={()=>setModal(null)}>Отмена</Btn><Btn onClick={save}>Сохранить</Btn></>}>
          <Input label="Название" value={form.name} onChange={v=>setForm(p=>({...p,name:v}))} placeholder="Напр. Главный вход"/>
          <Input label="Местоположение" value={form.location} onChange={v=>setForm(p=>({...p,location:v}))} placeholder="Напр. 1 этаж"/>
          <Select label="Город" value={form.city_id} onChange={v=>setForm(p=>({...p,city_id:v}))}
            options={cityOptions} placeholder="Выберите город"/>
        </Modal>
      )}
    </div>
  );
}

function Structure(){
  const [tab,setTab]=useState("companies");
  const [companies,setCompanies]=useState([]);
  const [cities,setCities]=useState([]);
  const [depts,setDepts]=useState([]);
  const [controllers,setCtrls]=useState([]);
  const [modal,setModal]=useState(null);
  const [form,setForm]=useState({});

  const load=async()=>{
    const [co,ci,d,c]=await Promise.all([
      api.get("/api/companies"),api.get("/api/cities"),
      api.get("/api/departments"),api.get("/api/controllers"),
    ]);
    setCompanies(co);setCities(ci);setDepts(d);setCtrls(c);
  };
  useEffect(()=>{load();},[]);

  const openModal=(type,item=null)=>{
    setModal({type,item});
    if(type==="company") setForm(item||{name:"",short_name:""});
    if(type==="city")    setForm(item||{name:"",company_id:""});
    if(type==="dept"){
      const ctrlIds=item?.controller_ips
        ?item.controller_ips.split(",").map(ip=>controllers.find(c=>c.ip===ip)?.id).filter(Boolean)
        :[];
      setForm(item?{...item,controller_ids:ctrlIds}:{name:"",city_id:"",color:"#6366f1",controller_ids:[]});
    }
  };

  const save=async()=>{
    const {type,item}=modal;
    if(type==="company"){
      if(item) await api.put(`/api/companies/${item.id}`,form);
      else await api.post("/api/companies",form);
    }
    if(type==="city"){
      const body={...form,company_id:Number(form.company_id)};
      if(item) await api.put(`/api/cities/${item.id}`,body);
      else await api.post("/api/cities",body);
    }
    if(type==="dept"){
      const body={...form,city_id:Number(form.city_id)||null,controller_ids:form.controller_ids||[]};
      if(item) await api.put(`/api/departments/${item.id}`,body);
      else await api.post("/api/departments",body);
    }
    setModal(null); load();
  };

  const del=async(type,id)=>{
    if(!confirm("Удалить?")) return;
    if(type==="company") await api.del(`/api/companies/${id}`);
    if(type==="city")    await api.del(`/api/cities/${id}`);
    if(type==="dept")    await api.del(`/api/departments/${id}`);
    load();
  };

  const toggleCtrl=id=>setForm(p=>({...p,
    controller_ids:p.controller_ids?.includes(id)
      ?p.controller_ids.filter(x=>x!==id)
      :[...(p.controller_ids||[]),id]
  }));

  return(
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-slate-800">Структура организации</h2>
        <Btn onClick={()=>openModal(tab==="companies"?"company":tab==="cities"?"city":"dept")}>+ Добавить</Btn>
      </div>
      <div className="flex gap-1 mb-6 bg-slate-100 p-1 rounded-lg w-fit">
        {[["companies","🏛 Компании"],["cities","🏙 Города"],["departments","🏢 Подразделения"]].map(([k,l])=>(
          <button key={k} onClick={()=>setTab(k)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors
              ${tab===k?"bg-white shadow text-slate-800":"text-slate-500 hover:text-slate-700"}`}>{l}</button>
        ))}
      </div>

      {tab==="companies"&&(
        <div className="grid gap-4 md:grid-cols-2">
          {companies.map(c=>(
            <div key={c.id} className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-slate-800">{c.name}</h3>
                  {c.short_name&&<p className="text-sm text-slate-500">{c.short_name}</p>}
                  <div className="flex gap-3 mt-2 text-sm text-slate-500">
                    <span>🏙 {c.city_count} городов</span>
                    <span>🏢 {c.dept_count} подразделений</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={()=>openModal("company",c)} className="text-blue-500">✏️</button>
                  <button onClick={()=>del("company",c.id)} className="text-red-400">🗑</button>
                </div>
              </div>
            </div>
          ))}
          {companies.length===0&&<p className="text-slate-400 col-span-2 text-center py-10">Нет компаний — добавьте первую</p>}
        </div>
      )}

      {tab==="cities"&&(
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {cities.map(c=>(
            <div key={c.id} className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-slate-400 mb-1">{c.company_name}</p>
                  <h3 className="font-semibold text-slate-800">🏙 {c.name}</h3>
                  <p className="text-sm text-slate-500 mt-1">🏢 {c.dept_count} подразделений</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={()=>openModal("city",c)} className="text-blue-500">✏️</button>
                  <button onClick={()=>del("city",c.id)} className="text-red-400">🗑</button>
                </div>
              </div>
            </div>
          ))}
          {cities.length===0&&<p className="text-slate-400 col-span-3 text-center py-10">Нет городов</p>}
        </div>
      )}

      {tab==="departments"&&(
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 uppercase text-xs">
              <tr>
                <th className="px-4 py-3 text-left">Подразделение</th>
                <th className="px-4 py-3 text-left">Компания / Город</th>
                <th className="px-4 py-3 text-left">Сотрудников</th>
                <th className="px-4 py-3 text-left">Контроллеры</th>
                <th className="px-4 py-3"/>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {depts.map(d=>(
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{background:d.color}}/>
                      <span className="font-medium">{d.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{d.company_name} / {d.city_name||"—"}</td>
                  <td className="px-4 py-3">{d.emp_count}</td>
                  <td className="px-4 py-3">
                    {d.ctrl_count>0
                      ?<Badge color="blue">{d.ctrl_count} контр.</Badge>
                      :<span className="text-slate-400 text-xs">нет доступа</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-end">
                      <button onClick={()=>openModal("dept",d)} className="text-blue-500">✏️</button>
                      <button onClick={()=>del("dept",d.id)} className="text-red-400">🗑</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {depts.length===0&&<div className="text-center text-slate-400 py-10">Нет подразделений</div>}
        </div>
      )}

      {modal&&(
        <Modal
          title={modal.item
            ?`Редактировать ${modal.type==="company"?"компанию":modal.type==="city"?"город":"подразделение"}`
            :`Новое ${modal.type==="company"?"подразделение компании":modal.type==="city"?"город":"подразделение"}`}
          onClose={()=>setModal(null)}
          footer={<><Btn color="gray" onClick={()=>setModal(null)}>Отмена</Btn><Btn onClick={save}>Сохранить</Btn></>}>

          {modal.type==="company"&&<>
            <Input label="Название компании" value={form.name} onChange={v=>setForm(p=>({...p,name:v}))}/>
            <Input label="Краткое название" value={form.short_name} onChange={v=>setForm(p=>({...p,short_name:v}))}/>
          </>}

          {modal.type==="city"&&<>
            <Select label="Компания" value={form.company_id} onChange={v=>setForm(p=>({...p,company_id:v}))}
              options={companies.map(c=>({value:c.id,label:c.name}))}/>
            <Input label="Название города" value={form.name} onChange={v=>setForm(p=>({...p,name:v}))}/>
          </>}

          {modal.type==="dept"&&<>
            <Select label="Город" value={form.city_id} onChange={v=>setForm(p=>({...p,city_id:v}))}
              options={cities.map(c=>({value:c.id,label:`${c.company_name} / ${c.name}`}))}/>
            <Input label="Название подразделения" value={form.name} onChange={v=>setForm(p=>({...p,name:v}))}/>
            <div>
              <label className="block text-sm font-medium text-slate-600 mb-1">Цвет</label>
              <input type="color" value={form.color||"#6366f1"}
                onChange={e=>setForm(p=>({...p,color:e.target.value}))}
                className="w-12 h-10 rounded border border-slate-200 cursor-pointer"/>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-600 mb-2">
                Доступ к контроллерам ({(form.controller_ids||[]).length} выбрано)
              </label>
              <div className="space-y-1 max-h-48 overflow-auto border border-slate-200 rounded-lg p-2">
                {controllers.map(c=>(
                  <label key={c.id} className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer">
                    <input type="checkbox"
                      checked={(form.controller_ids||[]).includes(c.id)}
                      onChange={()=>toggleCtrl(c.id)} className="rounded"/>
                    <span className={`w-2 h-2 rounded-full ${c.online?"bg-green-500":"bg-red-400"}`}/>
                    <div>
                      <p className="text-sm font-medium">{c.name||c.ip}</p>
                      <p className="text-xs text-slate-400">{c.ip}{c.location&&` • ${c.location}`}</p>
                    </div>
                  </label>
                ))}
                {controllers.length===0&&<p className="text-slate-400 text-sm text-center py-2">Нет контроллеров</p>}
              </div>
            </div>
          </>}
        </Modal>
      )}
    </div>
  );
}

function Reports(){
  const [tab,setTab]=useState("employee");
  const [employees,setEmps]=useState([]);
  const [empId,setEmpId]=useState("");
  const [dateFrom,setFrom]=useState(new Date().toISOString().slice(0,10));
  const [dateTo,setTo]=useState(new Date().toISOString().slice(0,10));
  const [report,setReport]=useState(null);
  const [presence,setPresence]=useState(null);

  useEffect(()=>{api.get("/api/employees").then(setEmps);},[]);

  const runReport=async()=>{
    if(!empId) return;
    const r=await api.get(`/api/report/employee/${empId}?date_from=${dateFrom}T00:00:00&date_to=${dateTo}T23:59:59`);
    setReport(r);
  };
  const runPresence=async()=>{
    const r=await api.get(`/api/report/presence?date=${dateFrom}`);
    setPresence(r);
  };
  const calcHours=row=>{
    if(!row.first_in||!row.last_out) return "—";
    const ms=new Date(row.last_out)-new Date(row.first_in);
    return `${Math.floor(ms/3600000)}ч ${Math.floor((ms%3600000)/60000)}м`;
  };

  return(
    <div>
      <h2 className="text-xl font-bold text-slate-800 mb-6">Отчёты</h2>
      <div className="flex gap-1 mb-6 bg-slate-100 p-1 rounded-lg w-fit">
        {[["employee","По сотруднику"],["presence","Присутствие"]].map(([k,l])=>(
          <button key={k} onClick={()=>setTab(k)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors
              ${tab===k?"bg-white shadow text-slate-800":"text-slate-500 hover:text-slate-700"}`}>{l}</button>
        ))}
      </div>
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-6 mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          {tab==="employee"&&(
            <div className="flex-1 min-w-48">
              <label className="block text-sm font-medium text-slate-600 mb-1">Сотрудник</label>
              <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
                value={empId} onChange={e=>setEmpId(e.target.value)}>
                <option value="">Выберите сотрудника</option>
                {employees.map(e=><option key={e.id} value={e.id}>{e.full_name}</option>)}
              </select>
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">С</label>
            <input type="date" value={dateFrom} onChange={e=>setFrom(e.target.value)}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none"/>
          </div>
          {tab==="employee"&&(
            <div>
              <label className="block text-sm font-medium text-slate-600 mb-1">По</label>
              <input type="date" value={dateTo} onChange={e=>setTo(e.target.value)}
                className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none"/>
            </div>
          )}
          <Btn onClick={tab==="employee"?runReport:runPresence}>Построить</Btn>
        </div>
      </div>

      {tab==="employee"&&report&&(
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 uppercase text-xs">
              <tr>
                <th className="px-4 py-3 text-left">Дата</th>
                <th className="px-4 py-3 text-left">Первый вход</th>
                <th className="px-4 py-3 text-left">Последний выход</th>
                <th className="px-4 py-3 text-left">Итого</th>
                <th className="px-4 py-3 text-left">Событий</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {report.report.map(row=>(
                <tr key={row.date} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium">{fmtDate(row.date)}</td>
                  <td className="px-4 py-3 text-green-600">{row.first_in?fmtTime(row.first_in):"—"}</td>
                  <td className="px-4 py-3 text-red-500">{row.last_out?fmtTime(row.last_out):"—"}</td>
                  <td className="px-4 py-3 font-semibold">{calcHours(row)}</td>
                  <td className="px-4 py-3 text-slate-500">{row.events.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {report.report.length===0&&<div className="text-center text-slate-400 py-10">Нет данных за период</div>}
        </div>
      )}

      {tab==="presence"&&presence&&(
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
          <div className="px-6 py-4 border-b font-semibold text-slate-800">
            На месте: {presence.present.length} чел.
          </div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 uppercase text-xs">
              <tr>
                <th className="px-4 py-3 text-left">Фото</th>
                <th className="px-4 py-3 text-left">Сотрудник</th>
                <th className="px-4 py-3 text-left">Подразделение</th>
                <th className="px-4 py-3 text-left">Вход</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {presence.present.map(p=>(
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2"><Avatar photo={p.photo} name={p.full_name} size={9}/></td>
                  <td className="px-4 py-3 font-medium">{p.full_name}</td>
                  <td className="px-4 py-3 text-slate-500">{p.department}</td>
                  <td className="px-4 py-3 text-green-600">{fmtTime(p.last_in)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {presence.present.length===0&&<div className="text-center text-slate-400 py-10">Никого нет на месте</div>}
        </div>
      )}
    </div>
  );
}

const PAGES=[
  {id:"monitor",    label:"Мониторинг",  icon:"📡", comp:Monitor},
  {id:"employees",  label:"Сотрудники",  icon:"👥", comp:Employees},
  {id:"controllers",label:"Контроллеры", icon:"🖥",  comp:Controllers},
  {id:"structure",  label:"Структура",   icon:"🏢", comp:Structure},
  {id:"reports",    label:"Отчёты",      icon:"📊", comp:Reports},
];

export default function App(){
  const [user,setUser]=useState(null);
  const [page,setPage]=useState("monitor");
  if(!user) return <Login onLogin={setUser}/>;
  const Page=PAGES.find(p=>p.id===page)?.comp||Monitor;
  return(
    <div className="min-h-screen bg-slate-50 flex">
      <aside className="w-56 bg-slate-900 text-white flex flex-col flex-shrink-0">
        <div className="px-6 py-5 border-b border-slate-700">
          <h1 className="font-bold text-lg">СКУД КЕЛЕТ</h1>
          <p className="text-slate-400 text-xs mt-0.5">{user.full_name}</p>
        </div>
        <nav className="flex-1 py-4 px-3 space-y-1">
          {PAGES.map(p=>(
            <button key={p.id} onClick={()=>setPage(p.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                ${page===p.id?"bg-blue-600 text-white":"text-slate-300 hover:bg-slate-800 hover:text-white"}`}>
              <span>{p.icon}</span>{p.label}
            </button>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-700">
          <button onClick={()=>setUser(null)}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
            🚪 Выйти
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto p-8"><Page/></div>
      </main>
    </div>
  );
}