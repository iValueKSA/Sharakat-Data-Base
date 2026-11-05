const {execFileSync}=require('child_process');
const crypto=require('crypto');
const {request}=require('C:/Users/QusaiAbdElhalim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const password=crypto.randomBytes(24).toString('base64url');
 let reset=false;
 try{
  const resetRaw=execFileSync('docker',['exec','-i','-e','PYTHONPATH=/app','-w','/app','alahsa-local-api-1','python','/tmp/reset_admin_local_once.py'],{input:JSON.stringify({password}),encoding:'utf8',stdio:['pipe','pipe','pipe']});
  const resetResult=JSON.parse(resetRaw.trim());
  if(!resetResult.ok)throw new Error('local reset rejected: '+resetResult.reason);
  reset=true;
  const ctx=await request.newContext({baseURL:'http://localhost:8080'});
  const wrong=await ctx.post('/api/auth/login',{data:{email:'admin@local',password:'Intentional-Wrong-Password-For-Verification!'}});
  const wrongRejected=wrong.status()===401;
  const login=await ctx.post('/api/auth/login',{data:{email:'admin@local',password}});
  let user=null,protectedUsers=null,protectedStatus=0;
  if(login.status()===200){const body=await login.json();user=body.user;const protectedResponse=await ctx.get('/api/admin/users');protectedStatus=protectedResponse.status();if(protectedStatus===200)protectedUsers=await protectedResponse.json();}
  const valid=login.status()===200&&user?.email==='admin@local'&&(user?.role||'').toLowerCase()==='admin';
  const access=protectedStatus===200&&Array.isArray(protectedUsers)&&protectedUsers.some(u=>u.email==='admin@local'&&u.is_active&&(u.role||'').toLowerCase()==='admin');
  const result={temporary_password:password,password_reset:true,reset_result:resetResult,wrong_password_status:wrong.status(),wrong_password_rejected:wrongRejected,valid_login:valid,login_status:login.status(),login_user:user?{email:user.email,role:user.role}:null,protected_admin_access:access,protected_status:protectedStatus,login_context_not_logged_out:true};
  process.stdout.write(JSON.stringify(result));
  await ctx.dispose();
  if(!wrongRejected||!valid||!access)process.exitCode=1;
 }catch(e){
  process.stdout.write(JSON.stringify({temporary_password:reset?password:null,password_reset:reset,verification_error:String(e.message||e)}));process.exitCode=1;
 }
})();
