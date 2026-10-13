import {Client} from '/Users/a112233/.npm/_npx/af752b90495482d7/node_modules/@modelcontextprotocol/client/dist/index.mjs';
import {StdioClientTransport} from '/Users/a112233/.npm/_npx/af752b90495482d7/node_modules/@modelcontextprotocol/client/dist/stdio.mjs';
import fs from 'node:fs';
const client=new Client({name:'jasper-rea-verification',version:'1.0.0'});
const transport=new StdioClientTransport({command:'/usr/local/bin/npx',args:['-y','rea-agents@6.4.0','mcp'],stderr:'pipe'});
try{await client.connect(transport);const listed=await client.listTools();fs.writeFileSync('/tmp/rea-tools.json',JSON.stringify(listed,null,2));const result=await client.callTool({name:'analyze_javascript_application',arguments:{input_path:'/tmp/rea-verification-app',format:'directory'}});fs.writeFileSync('/tmp/rea-analysis-test.json',JSON.stringify(result,null,2));console.log(JSON.stringify({server:client.getServerVersion(),toolCount:listed.tools.length,isError:result.isError||false,contentPreview:JSON.stringify(result).slice(0,2000)}));}finally{await client.close();}
