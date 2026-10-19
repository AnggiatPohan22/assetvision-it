import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { JSDOM } from "jsdom";
import { act, type ReactNode } from "react";
import { CatalogProvider } from "../components/catalog/shared";
import RecognitionWorkspace from "../components/recognition/recognition-workspace";
import SurveyDetail from "../components/recognition/survey-detail";
import type { Survey } from "../lib/recognition";
import type { Role } from "../lib/catalog";
const dom=new JSDOM("<!doctype html><html><body></body></html>",{url:"http://localhost:3000"});
const win=dom.window;
Object.assign(globalThis,{window:win,document:win.document,HTMLElement:win.HTMLElement,HTMLInputElement:win.HTMLInputElement,HTMLSelectElement:win.HTMLSelectElement,HTMLTextAreaElement:win.HTMLTextAreaElement,Event:win.Event,MouseEvent:win.MouseEvent,IS_REACT_ACT_ENVIRONMENT:true});
Object.defineProperty(globalThis,"navigator",{value:win.navigator,configurable:true});
const reactDomClient=import("react-dom/client");
let container:HTMLDivElement;let root:import("react-dom/client").Root;
const originalFetch=globalThis.fetch;
const id="00000000-0000-0000-0000-000000000005";
const survey:Survey={id,version:1,created_by:"officer",created_at:"2026-10-19T00:00:00Z",observed_at:"2026-10-19T00:00:00Z",device_job_id:id,label_job_id:null,notes:"Synthetic observation",review_status:"PENDING",asset_id:null,review:null,evidence:{
 visual:{status:"UNCERTAIN",reason:"UNCALIBRATED_SIMILARITY_ONLY",encoder:{name:"test encoder",version:"v1"},candidates:[{device_model_id:"model",rank:1,similarity:0.9123}]},
 ocr:{raw_text:"SN: RAW789",corrected_text:"SN: ABC789XYZ",reason:"review",engine_version:"synthetic",ocr_candidates:[],manual_candidates:[{kind:"SERIAL_NUMBER",raw_value:"ABC789XYZ",normalized_value:"ABC789XYZ",source:"MANUAL",issues:[]}]},
 location_name:"Lounge",force_unknown:false,fusion:{status:"PROBABLE_ASSET",reasons:["LABEL_REVIEW_REQUIRED"],candidates:[{asset_id:"asset",reasons:["IDENTIFIER_MATCH"]}]},
 unit_snapshots:[{asset_id:"asset",asset_version:3,device_model_id:"model",manufacturer_id:"maker",archived:false,claims:[{kind:"SERIAL_NUMBER",value:"ABC789XYZ",verification:"VERIFIED",source:"MANUAL"}]}],asset_codes:{asset:"AP-001"},model_names:{model:"Synthetic AP"}}};
let writes:{path:string;init:RequestInit}[];
function mock(fail=false){globalThis.fetch=async(url,init={})=>{const path=String(url);
 if(path.endsWith("/auth/session"))return Response.json({csrf_token:"test-csrf"});
 if(init.method){writes.push({path,init});if(fail)return Response.json({detail:"changed"},{status:409});
  if(path.endsWith("/model-candidates"))return Response.json({id,content_url:"/private",result:{status:"UNKNOWN_MODEL",reason:"EMPTY_INDEX",encoder:null,candidates:[]}});
  if(path.endsWith("/review"))return Response.json({...survey,review_status:"MATCH"});
  return Response.json(survey);
 }
 if(path.endsWith("/recognition/jobs"))return Response.json({items:[]});
 if(path.includes("/locations/tree"))return Response.json({items:[],total:0});
 if(path.includes("/device-models?"))return Response.json({items:[],total:0,total_pages:0});
 if(path.includes("/recognition/observations?"))return Response.json({items:[],page:1,total:0,total_pages:0});
 throw new Error(path);
};}
async function settle(){await act(async()=>{await new Promise(r=>setTimeout(r,8));});}
async function render(node:ReactNode,role:Role="ADMIN"){await act(async()=>root.render(<CatalogProvider role={role}>{node}</CatalogProvider>));await settle();}
function field(text:string){const item=Array.from(container.querySelectorAll("label")).find(l=>l.textContent?.startsWith(text))?.querySelector<HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement>("input,select,textarea");assert.ok(item,text);return item;}
async function change(item:HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement,value:string){const proto=item instanceof win.HTMLSelectElement?win.HTMLSelectElement.prototype:item instanceof win.HTMLTextAreaElement?win.HTMLTextAreaElement.prototype:win.HTMLInputElement.prototype;await act(async()=>{Object.getOwnPropertyDescriptor(proto,"value")!.set!.call(item,value);item.dispatchEvent(new win.Event("input",{bubbles:true}));item.dispatchEvent(new win.Event("change",{bubbles:true}));});}
async function submit(form:HTMLFormElement){await act(async()=>{form.dispatchEvent(new win.Event("submit",{bubbles:true,cancelable:true}));});await settle();}
beforeEach(async()=>{writes=[];const {createRoot}=await reactDomClient;container=document.createElement("div");document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();globalThis.fetch=originalFetch;});

test("VIEWER reads without upload or review controls",async()=>{mock();await render(<RecognitionWorkspace/>,"VIEWER");assert.ok(!container.querySelector('input[type="file"]'));assert.match(container.textContent!,/Riwayat observasi/);await render(<SurveyDetail observation={survey} onReviewed={()=>undefined}/>,"VIEWER");assert.ok(!container.querySelector("form"));assert.match(container.textContent!,/Menunggu review ADMIN/);});
test("detail keeps raw correction similarity and unit separate",async()=>{mock();await render(<SurveyDetail observation={survey} onReviewed={()=>undefined}/>,"OFFICER");assert.match(container.textContent!,/SN: RAW789/);assert.match(container.textContent!,/SN: ABC789XYZ/);assert.match(container.textContent!,/similarity 0.9123/);assert.match(container.textContent!,/AP-001/);assert.match(container.textContent!,/Synthetic AP/);assert.ok(!container.textContent!.includes("confidence"));});
test("ADMIN match requires explicit label confirmation and retained manual identifier",async()=>{mock();await render(<SurveyDetail observation={survey} onReviewed={()=>undefined}/>);await change(field("Keputusan"),"MATCH");await change(field("Unit yang diperiksa"),"asset");const button=container.querySelector('button[type="submit"]') as HTMLButtonElement;assert.equal(button.disabled,true);const checks=container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');await act(async()=>checks.forEach(c=>c.click()));await change(field("Alasan review"),"Label physically checked");assert.equal(button.disabled,false);await submit(container.querySelector("form")!);const body=JSON.parse(String(writes[0].init.body));assert.equal(body.asset_version,3);assert.deepEqual(body.checked_manual_indices,[0]);assert.equal(body.label_checked,true);assert.equal(body.manufacturer_id,"maker");});
test("failed review preserves draft and blocks duplicate submit",async()=>{mock(true);await render(<SurveyDetail observation={survey} onReviewed={()=>undefined}/>);await change(field("Alasan review"),"Need clearer photo");const form=container.querySelector("form")!;await submit(form);assert.equal(field("Alasan review").value,"Need clearer photo");assert.equal(container.querySelector("fieldset")!.disabled,true);await submit(form);assert.equal(writes.length,1);});
test("conflict shows actionable warning and human explanations",async()=>{mock();await render(<SurveyDetail observation={{...survey,evidence:{...survey.evidence,fusion:{...survey.evidence.fusion,status:"CONFLICT",reasons:["OFFICIAL_LOCATION_CONFLICT"]}}}} onReviewed={()=>undefined}/>);assert.match(container.textContent!,/Bukti bertentangan/);assert.match(container.textContent!,/Lokasi pengamatan berbeda/);});
test("OFFICER uploads one photo then can record unknown with manual correction",async()=>{mock();await render(<RecognitionWorkspace/>,"OFFICER");const input=field("Foto perangkat") as HTMLInputElement;Object.defineProperty(input,"files",{value:[new File(["synthetic"],"test.png",{type:"image/png"})],configurable:true});await act(async()=>input.dispatchEvent(new win.Event("change",{bubbles:true})));await submit(container.querySelector("form")!);assert.equal(writes.length,1);assert.ok(writes[0].init.body instanceof FormData);assert.match(container.textContent!,/Analisis visual belum tersedia/);await change(field("Catatan observasi"),"New unknown device");await change(field("Koreksi label manual"),"SN: ABC789XYZ");await act(async()=>(field("Tidak dikenali") as HTMLInputElement).click());await submit(container.querySelector("form")!);const body=JSON.parse(String(writes[1].init.body));assert.equal(body.force_unknown,true);assert.equal(body.correction.corrected_text,"SN: ABC789XYZ");assert.ok(body.request_id);assert.equal(body.device_job_id,id);});


test("malformed successful upload keeps uncertain result blocked",async()=>{
 mock();const base=globalThis.fetch;globalThis.fetch=async(url,init)=>init?.method?Response.json({}):base(url,init);
 await render(<RecognitionWorkspace/>,"OFFICER");const input=field("Foto perangkat") as HTMLInputElement;
 Object.defineProperty(input,"files",{value:[new File(["synthetic"],"test.png",{type:"image/png"})],configurable:true});
 await act(async()=>input.dispatchEvent(new win.Event("change",{bubbles:true})));
 await submit(container.querySelector("form")!);assert.match(container.textContent!,/hasil belum pasti/);
 assert.equal(container.querySelector("fieldset")!.disabled,true);
});
test("pending photo can be recovered without a duplicate upload",async()=>{
 mock();const base=globalThis.fetch;globalThis.fetch=async(url,init)=>String(url).endsWith("/recognition/jobs")?Response.json({items:[{id,kind:"MODEL",content_url:"/private",result:{status:"UNKNOWN_MODEL",reason:"EMPTY_INDEX",encoder:null,candidates:[]}}]}):base(url,init);
 await render(<RecognitionWorkspace/>,"OFFICER");const recover=Array.from(container.querySelectorAll("button")).find(b=>b.textContent?.startsWith("Gunakan foto"));assert.ok(recover);
 await act(async()=>recover.click());await settle();assert.match(container.textContent!,/Hasil awal/);assert.equal(writes.length,0);
 await change(field("Catatan observasi"),"Recovered evidence");await submit(container.querySelector("form")!);
 assert.equal(writes.length,1);assert.equal(JSON.parse(String(writes[0].init.body)).device_job_id,id);
});


test("changing the photo clears manual label and preserves pending evidence",async()=>{
 mock();const base=globalThis.fetch;globalThis.fetch=async(url,init)=>String(url).endsWith("/recognition/jobs")?Response.json({items:[{id,kind:"MODEL",content_url:"/private",result:{status:"UNKNOWN_MODEL",reason:"EMPTY_INDEX",encoder:null,candidates:[]}}]}):base(url,init);
 await render(<RecognitionWorkspace/>,"OFFICER");const recover=Array.from(container.querySelectorAll("button")).find(b=>b.textContent?.startsWith("Gunakan foto"))!;
 await act(async()=>recover.click());await change(field("Koreksi label manual"),"SN: OLDLABEL");
 const cancel=Array.from(container.querySelectorAll("button")).find(b=>b.textContent?.startsWith("Pilih foto lain"))!;
 await act(async()=>cancel.click());const again=Array.from(container.querySelectorAll("button")).find(b=>b.textContent?.startsWith("Gunakan foto"));assert.ok(again);
 await act(async()=>again.click());assert.equal(field("Koreksi label manual").value,"");assert.equal(writes.length,0);
});
