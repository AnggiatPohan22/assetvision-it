import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { JSDOM } from "jsdom";
import { act, useState, type ReactNode } from "react";
import { CatalogProvider } from "../components/catalog/shared";
import LocationManager from "../components/locations/location-manager";
import AssetLocation from "../components/locations/asset-location";
import MovementInbox, { MovementList } from "../components/locations/movements";
import { descendants, treeRows, reasonValue, type Location, type LocationStatus, type Movement, type Observation } from "../lib/locations";
import type { Asset } from "../lib/assets";
import type { Role } from "../lib/catalog";

const dom=new JSDOM("<!doctype html><html><body></body></html>",{url:"http://localhost:3000"});
const win=dom.window;
Object.assign(globalThis,{window:win,document:win.document,HTMLElement:win.HTMLElement,HTMLInputElement:win.HTMLInputElement,HTMLSelectElement:win.HTMLSelectElement,HTMLTextAreaElement:win.HTMLTextAreaElement,Event:win.Event,MouseEvent:win.MouseEvent,IS_REACT_ACT_ENVIRONMENT:true});
Object.defineProperty(globalThis,"navigator",{value:win.navigator,configurable:true});
const reactDomClient=import("react-dom/client");
let container:HTMLDivElement; let root:import("react-dom/client").Root;
const originalFetch=globalThis.fetch;
const origin:Location={id:"00000000-0000-0000-0000-000000000011",parent_id:null,code:"villa-1",name:"Villa 1",kind:"BUILDING",is_active:true,version:1,latitude:null,longitude:null,gps_accuracy_m:null,gps_recorded_at:null};
const destination:Location={...origin,id:"00000000-0000-0000-0000-000000000010",code:"villa-10",name:"Villa 10"};
const asset:Asset={id:"00000000-0000-0000-0000-000000000003",asset_code:"AP-003",device_model_id:"model",lifecycle_status:"IN_USE",condition:"GOOD",notes:null,purchase_date:null,installed_at:null,created_at:"2026-10-19T00:00:00Z",updated_at:"2026-10-19T00:00:00Z",version:3};
const observation:Observation={id:"observation",asset_id:asset.id,observed_location_id:origin.id,observed_by:"officer",observed_at:"2026-10-19T01:00:00Z",recorded_at:"2026-10-19T02:00:00Z",evidence_note:"Synthetic seen in Villa 1",comparison_status:"LOCATION_CONFLICT",review_status:"PENDING",reviewed_by:null,reviewed_at:null,review_reason:null,snapshot_json:{observed_location:origin,official_location:destination},version:1};
const state:LocationStatus={asset_id:asset.id,asset_version:3,current_location_id:destination.id,location_verified_at:"2026-10-19T00:00:00Z",status:"LOCATION_CONFLICT",location_conflict:true,latest_observation:observation};
const movement:Movement={id:"movement",asset_id:asset.id,from_location_id:origin.id,to_location_id:destination.id,status:"PENDING",reason:"Synthetic move",requested_by:"officer",requested_at:"2026-10-19T00:00:00Z",expected_asset_version:3,request_snapshot_json:{from:origin,to:destination},reviewed_by:null,reviewed_at:null,review_reason:null,effective_at:null,version:1};
const page=(items:unknown[],total=items.length)=>({items,total,page:1,page_size:10,total_pages:Math.ceil(total/10)});
let writes:{path:string;body:Record<string,unknown>;init:RequestInit}[];
type Handler=(path:string,init:RequestInit)=>Response|Promise<Response>|undefined;
function mock(handler:Handler=()=>undefined) {
 globalThis.fetch=async(url,init={})=>{
  const path=String(url);
  if(path==="/api/v1/auth/session") return Response.json({csrf_token:"synthetic-csrf"});
  if(init.method) writes.push({path,body:JSON.parse(String(init.body)),init});
  const result=await handler(path,init); if(result) return result;
  if(init.method) return Response.json({id:"saved"});
  if(path==="/api/v1/locations/tree") return Response.json({items:[origin,destination],total:2});
  if(path.includes("/location-status")) return Response.json(state);
  if(path.includes("/location-observations?")) return Response.json(page([observation]));
  if(path.includes("/timeline?")) return Response.json(page([{id:"event",source:"LOCATION",actor_id:"admin",event_type:"MOVEMENT_APPROVED",occurred_at:"2026-10-19T00:00:00Z",recorded_at:"2026-10-19T00:00:00Z",payload_json:{from:origin.name,to:destination.name}}]));
  if(path.includes("/movements?")) return Response.json(page([movement]));
  if(path===`/api/v1/assets/${asset.id}`) return Response.json({...asset,current_location_id:origin.id});
  throw new Error("Unhandled "+path);
 };
}
async function settle(){await act(async()=>{await new Promise(resolve=>setTimeout(resolve,8));});}
async function render(node:ReactNode,role:Role="ADMIN",userId="admin"){await act(async()=>root.render(<CatalogProvider role={role} userId={userId}>{node}</CatalogProvider>));await settle();}
async function click(element:Element){await act(async()=>(element as HTMLElement).click());await settle();}
function button(text:string){const element=Array.from(container.querySelectorAll("button")).find(item=>item.textContent?.trim()===text);assert.ok(element,"Missing button "+text);return element;}
function input(label:string){const field=Array.from(container.querySelectorAll("label")).find(item=>item.textContent?.trim().startsWith(label))?.querySelector<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>("input,select,textarea");assert.ok(field,"Missing field "+label);return field;}
async function change(field:HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement,value:string){const proto=field instanceof win.HTMLSelectElement?win.HTMLSelectElement.prototype:field instanceof win.HTMLTextAreaElement?win.HTMLTextAreaElement.prototype:win.HTMLInputElement.prototype;await act(async()=>{Object.getOwnPropertyDescriptor(proto,"value")!.set!.call(field,value);field.dispatchEvent(new win.Event("input",{bubbles:true}));field.dispatchEvent(new win.Event("change",{bubbles:true}));});}
async function submit(form:Element){await act(async()=>form.dispatchEvent(new win.Event("submit",{bubbles:true,cancelable:true})));await settle();}
function Panel(){const [revision,setRevision]=useState(0);return <AssetLocation asset={asset} revision={revision} editable onChanged={()=>setRevision(value=>value+1)} onEditing={()=>undefined}/>;}
beforeEach(async()=>{writes=[];const {createRoot}=await reactDomClient;container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();globalThis.fetch=originalFetch;});

test("hierarchy order and descendant exclusion preserve archived ancestry",()=>{
 const child={...destination,parent_id:origin.id};
 assert.deepEqual(treeRows([child,origin]).map(row=>[row.item.name,row.depth]),[["Villa 1",0],["Villa 10",1]]);
 assert.deepEqual([...descendants(origin.id,[origin,child])],[origin.id,child.id]);
 assert.throws(()=>reasonValue("  "),/wajib/);assert.throws(()=>reasonValue("x".repeat(2001)),/2000/);assert.throws(()=>reasonValue("a\0b"),/dibaca/);
});

test("read-only hierarchy hides writes for OFFICER and VIEWER",async()=>{
 mock();for(const role of ["OFFICER","VIEWER"] as Role[]){await render(<LocationManager/>,role);assert.match(container.textContent!,/Villa 10/);assert.ok(!container.textContent!.includes("Tambah lokasi"));assert.ok(!container.textContent!.includes("Edit / arsip"));}assert.equal(writes.length,0);
});

test("ADMIN creates a child location with canonical code and session CSRF",async()=>{
 mock();await render(<LocationManager/>);await click(button("Tambah lokasi"));await change(input("Kode lokasi")," LOBBY ");await change(input("Nama lokasi"),"Lobby");await change(input("Induk lokasi"),origin.id);await change(input("Jenis lokasi"),"ROOM");await submit(container.querySelector("form")!);
 assert.deepEqual(writes[0].body,{code:"lobby",name:"Lobby",kind:"ROOM",parent_id:origin.id,is_active:true});assert.equal(writes[0].path,"/api/v1/locations");assert.equal((writes[0].init.headers as Record<string,string>)["X-CSRF-Token"],"synthetic-csrf");assert.match(container.textContent!,/Lokasi tersimpan/);
});

test("edit excludes descendants, freezes version and preserves draft on 409",async()=>{
 mock((path,init)=>init.method?Response.json({detail:"changed"},{status:409}):path.endsWith("/tree")?Response.json({items:[origin,{...destination,parent_id:origin.id}],total:2}):undefined);
 await render(<LocationManager/>);await click(container.querySelector('[aria-label="Edit Villa 1"]')!);
 assert.equal(input("Induk lokasi").querySelectorAll("option").length,1);
 await change(input("Nama lokasi"),"Keep draft");await click(input("Lokasi aktif"));await submit(container.querySelector("form")!);
 assert.equal(writes[0].body.version,1);assert.equal(writes[0].body.is_active,false);assert.ok(!("latitude" in writes[0].body));assert.equal(input("Nama lokasi").value,"Keep draft");assert.ok(button("Simpan lokasi").disabled);await submit(container.querySelector("form")!);assert.equal(writes.length,1);await click(button("Batalkan dan muat ulang"));assert.equal(container.querySelector("form"),null);
});

test("empty hierarchy, failed reads and session expiry provide recovery",async()=>{
 mock(()=>Response.json({items:[],total:0}));await render(<LocationManager/>);assert.match(container.textContent!,/Belum ada lokasi/);
 mock(()=>Response.json({detail:"expired"},{status:401}));await click(button("Muat ulang lokasi"));assert.ok(container.querySelector('a[href="/login"]'));assert.ok(button("Coba muat lagi"));
});

test("VIEWER sees official location, conflict badge, actors and immutable timeline only",async()=>{
 mock();await render(<Panel/>,"VIEWER");assert.match(container.textContent!,/LOCATION_CONFLICT/);assert.match(container.textContent!,/Villa 10/);assert.match(container.textContent!,/Perpindahan disetujui/);assert.match(container.textContent!,/Aktor admin/);assert.ok(!container.querySelector("form"));assert.equal(writes.length,0);assert.ok(!container.textContent!.includes("Catat observasi"));
});

test("OFFICER request uses frozen official version and does not optimistically move",async()=>{
 mock();await render(<Panel/>,"OFFICER","officer");await click(button("Ajukan perpindahan"));assert.ok(!Array.from(input("Lokasi tujuan").querySelectorAll("option")).some(item=>item.value===destination.id));await change(input("Lokasi tujuan"),origin.id);await change(input("Alasan perpindahan"),"Move explicitly");await submit(container.querySelector("form")!);
 assert.equal(writes[0].path,`/api/v1/assets/${asset.id}/movements`);assert.deepEqual(writes[0].body,{asset_version:3,to_location_id:origin.id,reason:"Move explicitly"});assert.match(container.textContent!,/LOCATION_CONFLICT/);assert.match(container.textContent!,/Villa 10/);
});

test("ADMIN initial placement is explicit and absent for OFFICER",async()=>{
 mock(path=>path.includes("/location-status")?Response.json({...state,current_location_id:null,location_verified_at:null,status:"UNPLACED",location_conflict:false}):undefined);
 await render(<Panel/>,"OFFICER");assert.ok(!container.textContent!.includes("Tetapkan lokasi awal"));await render(<Panel/>);await click(button("Tetapkan lokasi awal"));await change(input("Lokasi tujuan"),origin.id);await change(input("Alasan perpindahan"),"Initial verified");await submit(container.querySelector("form")!);assert.deepEqual(writes[0].body,{version:3,location_id:origin.id,reason:"Initial verified"});assert.match(writes[0].path,/initial-placement$/);
});

test("observation validates timezone then sends evidence without master fields",async()=>{
 mock();await render(<Panel/>,"OFFICER");await click(button("Catat observasi"));await change(input("Lokasi yang diamati"),origin.id);await change(input("Bukti / catatan"),"Seen in Villa 1");await change(input("Waktu observasi"),"2026-01-01T08:00:00");await submit(container.querySelector("form")!);assert.equal(writes.length,0);assert.match(container.textContent!,/zona waktu/);await change(input("Waktu observasi"),"2026-01-01T08:00:00+08:00");await submit(container.querySelector("form")!);assert.equal(writes[0].path,"/api/v1/location-observations");assert.deepEqual(writes[0].body,{asset_id:asset.id,asset_version:3,observed_location_id:origin.id,evidence_note:"Seen in Villa 1",observed_at:"2026-01-01T08:00:00+08:00"});
});

test("unknown save result retains evidence and blocks automatic or manual replay",async()=>{
 mock((_path,init)=>{if(init.method)throw new Error("offline");return undefined;});await render(<Panel/>,"OFFICER");await click(button("Catat observasi"));await change(input("Lokasi yang diamati"),origin.id);await change(input("Bukti / catatan"),"Keep evidence");await submit(container.querySelector("form")!);assert.equal(input("Bukti / catatan").value,"Keep evidence");assert.match(container.textContent!,/hasil belum diketahui/);assert.ok(button("Simpan observasi").disabled);await submit(container.querySelector("form")!);assert.equal(writes.length,1);
});

test("movement inbox shows snapshot/current/history and sends versioned approval",async()=>{
 mock();await render(<MovementInbox/>);await click(button("Review request"));assert.match(container.textContent!,/Villa 1 → Villa 10/);assert.match(container.textContent!,/Lokasi resmi saat review/);assert.match(container.textContent!,/ADMIN boleh/);await change(input("Alasan keputusan"),"Checked history");await submit(container.querySelector("form")!);assert.equal(writes[0].path,"/api/v1/movements/movement/approve");assert.deepEqual(writes[0].body,{version:1,reason:"Checked history"});
});

test("stale approval is blocked, but ADMIN can reject without changing location",async()=>{
 mock(path=>path===`/api/v1/assets/${asset.id}`?Response.json({...asset,version:4,current_location_id:destination.id}):undefined);await render(<MovementInbox/>);await click(button("Review request"));assert.match(container.textContent!,/Request stale/);await change(input("Alasan keputusan"),"Old request");await submit(container.querySelector("form")!);assert.equal(writes.length,0);await change(input("Keputusan"),"reject");await submit(container.querySelector("form")!);assert.equal(writes[0].path,"/api/v1/movements/movement/reject");assert.equal(writes[0].body.version,1);
});

test("OFFICER only sees own cancellation; VIEWER has no decisions",async()=>{
 mock();for(const [role,id] of [["OFFICER","other"],["VIEWER","officer"]] as [Role,string][]){await render(<MovementList items={[movement]} locations={[origin,destination]} onChanged={()=>undefined}/>,role,id);assert.ok(!container.querySelector("button"));}
 await render(<MovementList items={[movement]} locations={[origin,destination]} onChanged={()=>undefined}/>,"OFFICER","officer");await click(button("Batalkan request saya"));assert.equal(input("Keputusan").querySelectorAll("option").length,1);await change(input("Alasan keputusan"),"No longer needed");await submit(container.querySelector("form")!);assert.match(writes[0].path,/cancel$/);
});

test("observation review retains mismatch semantics and sends observation version",async()=>{
 mock();await render(<Panel/>);await click(button("Review observasi"));assert.match(container.textContent!,/tidak menghapus konflik/);await change(input("Alasan review"),"Reviewed evidence");await submit(container.querySelector("form")!);assert.deepEqual(writes[0].body,{version:1,review_status:"ACKNOWLEDGED",reason:"Reviewed evidence"});assert.match(writes[0].path,/location-observations\/observation\/review$/);assert.match(container.textContent!,/LOCATION_CONFLICT/);
});

test("timeline and inbox filters are read-only and reset pagination",async()=>{
 const reads:string[]=[];mock((path,init)=>{if(!init.method)reads.push(path);return undefined;});await render(<Panel/>,"VIEWER");await change(input("Jenis riwayat"),"METADATA");await settle();assert.ok(reads.some(path=>path.includes("source=METADATA")&&path.includes("page=1")));assert.equal(writes.length,0);
 await render(<MovementInbox/>);await change(input("Status request"),"REJECTED");await settle();assert.ok(reads.some(path=>path.includes("status=REJECTED")&&path.includes("page=1")));
});


test("two submits while save is pending create exactly one request",async()=>{
 let resolve!:(value:Response)=>void;
 mock((_path,init)=>init.method?new Promise<Response>(done=>{resolve=done;}):undefined);
 await render(<Panel/>,"OFFICER");await click(button("Catat observasi"));await change(input("Lokasi yang diamati"),origin.id);await change(input("Bukti / catatan"),"Only one evidence record");
 const form=container.querySelector("form")!;
 await act(async()=>{form.dispatchEvent(new win.Event("submit",{bubbles:true,cancelable:true}));form.dispatchEvent(new win.Event("submit",{bubbles:true,cancelable:true}));});await settle();
 assert.equal(writes.length,1);assert.ok(button("Menyimpan…").disabled);
 await act(async()=>resolve(Response.json({id:"saved"})));await settle();assert.equal(writes.length,1);
});

test("movement review fails closed while current/history reads are unavailable",async()=>{
 mock(path=>path===`/api/v1/assets/${asset.id}`?Response.json({detail:"unavailable"},{status:503}):undefined);
 await render(<MovementInbox/>);await click(button("Review request"));assert.ok(button("Konfirmasi keputusan").disabled);assert.match(container.textContent!,/belum dapat dihubungi/);assert.equal(writes.length,0);await click(button("Batalkan"));assert.equal(container.querySelector("form"),null);
});
