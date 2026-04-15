/** @NApiVersion 2.1 */
const salesorderSearchObj = search.create({
    type: "salesorder",
    settings:[{"name":"consolidationtype","value":"ACCTTYPE"},{"name":"includeperiodendtransactions","value":"F"}],
    filters:
    [
       ["type","anyof","SalesOrd"], 
       "AND", 
       ["status","anyof","SalesOrd:B","SalesOrd:D"], 
       "AND", 
       ["mainline","is","T"], 
       "AND", 
       ["printedpickingticket","is","F"], 
       "AND", 
       ["location","anyof","@ALL@"], 
       "AND", 
       ["formulanumeric: TRUNC({custbody10}) - TRUNC({today})","between","1","2"]
    ],
    columns:
    [
       search.createColumn({name: "tranid", label: "Document Number"}),
       search.createColumn({name: "entity", label: "Name"}),
       search.createColumn({name: "custbody11", label: "Installation option"}),
       search.createColumn({name: "custbody10", label: "Auxiliary Ship Date"}),
       search.createColumn({
          name: "formulahtml",
          formula: "'<a href=\"/app/site/hosting/scriptlet.nl?script=1052&deploy=1&custparam_orderid='||{internalid}||'\" target=\"_blank\">PRINT</a>'",
          label: "Print"
       })
    ]
 });
 const searchResultCount = salesorderSearchObj.runPaged().count;
 log.debug("salesorderSearchObj result count",searchResultCount);
 salesorderSearchObj.run().each(function(result){
    // .run().each has a limit of 4,000 results
    return true;
 });
 
 /*
 salesorderSearchObj.id="customsearch1776257434207";
 salesorderSearchObj.title="Picking Ticket Printout (copy)";
 const newSearchId = salesorderSearchObj.save();
 */