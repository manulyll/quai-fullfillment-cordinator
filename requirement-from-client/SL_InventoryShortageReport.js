/**
 * @NApiVersion 2.1
 * @NScriptType Suitelet
 * @NModuleScope SameAccount
 */
define(['N/search', 'N/ui/serverWidget', 'N/runtime', 'N/format'], (search, serverWidget, runtime, format) => {

    const ITEMS_TO_EXCLUDE = [
        2449, 2447, 2448, 2450, 2446, 6251, 6304, 6299, 
        6777, 6776, 7014, 7058, 1275, 1276, 5741, 2463
    ];

    const onRequest = (context) => {
        let request = context.request;
        let currentUser = runtime.getCurrentUser();

        // --- BILINGUAL DICTIONARY LOGIC ---
        let langPref = String(currentUser.getPreference({ name: 'LANGUAGE' }) || 'en_US').toLowerCase();
        let isFrench = langPref.includes('fr');

        const txt = {
            titleDetail: isFrench ? "Rapport détaillé des ruptures (2 sem)" : "2-Week Detailed Shortage Report",
            lblLocation: isFrench ? "Filtrer par emplacement" : "Filter by Location",
            lblStartDate: isFrench ? "Date de début" : "Start Date",
            lblEndDate: isFrench ? "Date de fin" : "End Date",
            btnRefresh: isFrench ? "Actualiser le rapport" : "Refresh Report",
            
            colDoc: isFrench ? "NUMÉRO DE DOCUMENT | ARTICLE" : "DOCUMENT NUMBER | ITEM",
            colCust: isFrench ? "CLIENT" : "CUSTOMER",
            colService: isFrench ? "SERVICE" : "SERVICE", // NEW COLUMN HEADER
            colDate: isFrench ? "DATE D'EXPÉDITION AUX" : "AUX SHIP DATE",
            colOrd: isFrench ? "COMMANDÉ" : "ORDERED",
            colHand: isFrench ? "EN STOCK" : "ON HAND",
            colRem: isFrench ? "RESTANT (Stock-Cmd)" : "REMAINING (OH-Ord)"
        };

        let form = serverWidget.createForm({ title: txt.titleDetail });

        // --- 1. BASELINE DATE LOGIC (The default 4-week window) ---
        let today = new Date();
        let daysUntilNextSunday = 14 - today.getDay();
        if (today.getDay() === 0) daysUntilNextSunday = 14; 
        let baseStartDate = new Date(today.getFullYear(), today.getMonth(), today.getDate() + daysUntilNextSunday);
        
        let baseEndDate = new Date(baseStartDate.getFullYear(), baseStartDate.getMonth(), baseStartDate.getDate() + 14);
        
        let nsBaseStartDate = format.format({ value: baseStartDate, type: format.Type.DATE });
        let nsBaseEndDate = format.format({ value: baseEndDate, type: format.Type.DATE });

        let paramStartDate = request.parameters.custpage_start_date || nsBaseStartDate;
        let paramEndDate = request.parameters.custpage_end_date || nsBaseEndDate;

        // --- 2. ADD FILTERS TO UI ---
        let isAdmin = [3, 1034, 1004].includes(currentUser.role);
        let selectedLocation;

        let filterGroup = form.addFieldGroup({ id: 'custpage_filters', label: ' ' });
        filterGroup.isSingleColumn = true; 

        if (isAdmin) {
            selectedLocation = request.parameters.custpage_location || '';
            let locField = form.addField({ id: 'custpage_location', type: serverWidget.FieldType.SELECT, source: 'location', label: txt.lblLocation, container: 'custpage_filters' });
            if (selectedLocation) locField.defaultValue = selectedLocation;
        } else {
            selectedLocation = currentUser.location;
        }

        // Date Filters
        let startDateField = form.addField({ id: 'custpage_start_date', type: serverWidget.FieldType.DATE, label: txt.lblStartDate, container: 'custpage_filters' });
        startDateField.defaultValue = paramStartDate;

        let endDateField = form.addField({ id: 'custpage_end_date', type: serverWidget.FieldType.DATE, label: txt.lblEndDate, container: 'custpage_filters' });
        endDateField.defaultValue = paramEndDate;

        form.addSubmitButton({ label: txt.btnRefresh });

        // ====================================================================
        // --- 3. HTML TABLE BUILDER ---
        // ====================================================================
        let htmlString = `
            <style>
                .custom-table { width: 100%; border-collapse: collapse; font-family: "Open Sans", Helvetica, sans-serif; font-size: 13px; margin-top: 15px;}
                .custom-table th, .custom-table td { padding: 6px 10px; border-bottom: 1px dashed #d3d3d3; text-align: center; }
                .custom-table th { background-color: #e5e5e5; color: #333; font-weight: bold; border-bottom: none;}
                
                /* Keep the first 3 columns (Item, Cust, Service) aligned to the left */
                .custom-table th:nth-child(1), .custom-table td:nth-child(1) { text-align: left; }
                .custom-table th:nth-child(2), .custom-table td:nth-child(2) { text-align: left; }
                .custom-table th:nth-child(3), .custom-table td:nth-child(3) { text-align: left; } 
                
                .parent-row { background-color: #f4f4f4; font-weight: bold; cursor: pointer; }
                .parent-row:hover { background-color: #e2e8f0; }
                .shortage-row { background-color: #ffebee !important; color: #b71c1c; font-weight: bold; }
                .toggle-icon { display: inline-block; width: 15px; margin-right: 10px; font-family: monospace; cursor: pointer; }
                .kit-row { background-color: #fafafa; }
            </style>
            <table class="custom-table">
                <thead><tr>
                    <th>${txt.colDoc}</th>
                    <th>${txt.colCust}</th>
                    <th>${txt.colService}</th>
                    <th>${txt.colDate}</th>
                    <th>${txt.colOrd}</th>
                    <th>${txt.colHand}</th>
                    <th>${txt.colRem}</th>
                </tr></thead><tbody>
        `;
            
        let detailDataArray = getDetailedData(selectedLocation, paramStartDate, paramEndDate);
        
        detailDataArray.forEach(soData => {
            let soNum = soData.soNum;
            
            htmlString += `
                <tr class="parent-row" onclick="toggleSO('${soNum}')">
                    <td colspan="2"><span class="toggle-icon" id="icon-${soNum}">[-]</span> ${soNum}</td>
                    <td>${soData.serviceType}</td> 
                    <td></td> 
                    <td style="font-weight: bold;">${soData.totalOrdered}</td>
                    <td colspan="2"></td> 
                </tr>
            `;

            soData.linesArr.forEach(line => {
                if (line.isKit) {
                    htmlString += `
                    <tr class="child-so-${soNum} level2-row kit-row shortage-row" onclick="toggleKit('${line.safeId}')">
                        <td style="padding-left: 25px;"><span class="toggle-icon kit-icon-${soNum}" id="icon-${line.safeId}">[+]</span> <strong>${line.itemName}</strong></td>
                        <td>${soData.customer}</td>
                        <td>${soData.serviceType}</td>
                        <td>${line.date}</td>
                        <td>${line.orderedQty}</td>
                        <td>-</td>
                        <td>-</td>
                    </tr>`;

                    line.components.forEach(comp => {
                        htmlString += `
                        <tr class="child-so-${soNum} child-kit-${line.safeId} shortage-row" style="display:none;">
                            <td style="padding-left: 60px; font-size: 12px;">&#8627; ${comp.itemName}</td>
                            <td></td> 
                            <td></td> 
                            <td></td> 
                            <td>${comp.orderedQty}</td>
                            <td>${comp.onHandQty}</td>
                            <td>${comp.remainingStock}</td>
                        </tr>`;
                    });
                } else {
                    htmlString += `
                    <tr class="child-so-${soNum} level2-row shortage-row">
                        <td style="padding-left: 25px;">${line.itemName}</td>
                        <td>${soData.customer}</td>
                        <td>${soData.serviceType}</td>
                        <td>${line.date}</td>
                        <td>${line.orderedQty}</td>
                        <td>${line.onHandQty}</td>
                        <td>${line.remainingStock}</td>
                    </tr>`;
                }
            });
        });

        htmlString += `
                </tbody>
            </table>
            <script>
                function toggleSO(soNum) {
                    let icon = document.getElementById('icon-' + soNum);
                    if (!icon) return;
                    let isHidden = icon.innerHTML === '[+]';
                    icon.innerHTML = isHidden ? '[-]' : '[+]';

                    document.querySelectorAll('.child-so-' + soNum + '.level2-row').forEach(row => {
                        row.style.display = isHidden ? '' : 'none';
                    });

                    if (!isHidden) {
                        document.querySelectorAll('.child-so-' + soNum + '[class*="child-kit-"]').forEach(row => {
                            row.style.display = 'none';
                        });
                        document.querySelectorAll('.kit-icon-' + soNum).forEach(icon => {
                            icon.innerHTML = '[+]';
                        });
                    }
                }

                function toggleKit(kitId) {
                    event.stopPropagation(); 
                    let icon = document.getElementById('icon-' + kitId);
                    if (!icon) return;
                    let isHidden = icon.innerHTML === '[+]';
                    icon.innerHTML = isHidden ? '[-]' : '[+]';

                    document.querySelectorAll('.child-kit-' + kitId).forEach(row => {
                        row.style.display = isHidden ? '' : 'none';
                    });
                }
            </script>
        `;

        let htmlField = form.addField({ id: 'custpage_report_html', type: serverWidget.FieldType.INLINEHTML, label: ' ' });
        htmlField.defaultValue = htmlString;
        htmlField.updateLayoutType({ layoutType: serverWidget.FieldLayoutType.OUTSIDEBELOW });

        context.response.writePage(form);
    };

    function getItemSortWeight(itemName) {
        let cleanName = itemName.replace(/<[^>]*>?/gm, '').split(':').pop().trim();
        let match = cleanName.match(/^(\d+)/);
        
        if (!match) return 5; 
        let prefix = parseInt(match[1], 10);
        
        if ((prefix >= 0 && prefix <= 99) || (prefix >= 600 && prefix <= 641)) return 1; 
        if (prefix >= 300 && prefix <= 499) return 2; 
        if ((prefix >= 100 && prefix <= 299) || (prefix >= 500 && prefix <= 599) || (prefix >= 642 && prefix <= 899)) return 3; 
        
        return 5; 
    }

    function extractCoreData(selectedLocation, startDateStr, endDateStr) {
        let filters = [
            ['mainline', 'is', 'F'], 'and',
            ['taxline', 'is', 'F'], 'and',
            ['shipping', 'is', 'F'], 'and',
            ['cogs', 'is', 'F'], 'and',
            ['status', 'anyof', ['SalesOrd:B', 'SalesOrd:D']], 'and', 
            ['custbody10', 'within', startDateStr, endDateStr]              
        ];

        if (selectedLocation) {
            filters.push('and', ['location', 'anyof', selectedLocation]);
        }

        let soSearch = search.create({
            type: search.Type.SALES_ORDER,
            filters: filters,
            columns: [
                search.createColumn({ name: 'tranid', sort: search.Sort.ASC }),
                search.createColumn({ name: 'entity' }),
                search.createColumn({ name: 'custbodyserviceprecis' }), // NEW COLUMN PULL
                search.createColumn({ name: 'line' }),
                search.createColumn({ name: 'item' }),
                search.createColumn({ name: 'quantity' }), 
                search.createColumn({ name: 'custbody10' }),
                search.createColumn({ name: 'memberitem', join: 'item' }),
                search.createColumn({ name: 'memberquantity', join: 'item' })
            ]
        });

        let soMap = {};
        let uniqueItemIds = [];

        let pagedData = soSearch.runPaged({ pageSize: 1000 });
        pagedData.pageRanges.forEach(pageRange => {
            let page = pagedData.fetch({ index: pageRange.index });
            page.data.forEach(result => {
                let soNum = result.getValue('tranid');
                let customerText = result.getText('entity') || '';
                let serviceType = result.getText('custbodyserviceprecis') || ''; // EXTRACT DROPDOWN TEXT
                let lineId = result.getValue('line');
                let topItemId = result.getValue('item');
                
                let rawName = result.getText('item') || '';
                let cleanItemName = rawName.split(':').pop().trim();

                if (/^MOD\s*-/i.test(cleanItemName)) return; 
                if (/^Description/i.test(cleanItemName)) return;
                let prefixMatch = cleanItemName.match(/^(\d+)/);
                if (prefixMatch && parseInt(prefixMatch[1], 10) >= 900) return;
                if (ITEMS_TO_EXCLUDE.includes(parseInt(topItemId))) return;

                let soQty = parseFloat(result.getValue('quantity')) || 0;
                let date = result.getValue('custbody10') || '';

                let memberItemId = result.getValue({ name: 'memberitem', join: 'item' });
                let memberQty = parseFloat(result.getValue({ name: 'memberquantity', join: 'item' })) || 0;
                let isKit = !!memberItemId;

                if (!soMap[soNum]) {
                    // ATTACH SERVICETYPE TO THE ORDER DATA
                    soMap[soNum] = { soNum: soNum, customer: customerText, serviceType: serviceType, date: date, totalOrdered: 0, lines: {}, processedLines: [] };
                }

                let itemKey = topItemId;

                if (!soMap[soNum].lines[itemKey]) {
                    soMap[soNum].lines[itemKey] = {
                        isKit: isKit,
                        itemName: cleanItemName,
                        orderedQty: 0,
                        date: date,
                        componentsMap: {},
                        safeId: 'kit_' + soNum.replace(/\W/g,'') + '_' + topItemId
                    };
                    if (!isKit && uniqueItemIds.indexOf(topItemId) === -1) uniqueItemIds.push(topItemId);
                }

                if (soMap[soNum].processedLines.indexOf(lineId) === -1) {
                    soMap[soNum].lines[itemKey].orderedQty += soQty;
                    soMap[soNum].totalOrdered += soQty;
                    soMap[soNum].processedLines.push(lineId);
                }

                if (isKit && memberItemId) {
                    let compName = result.getText({ name: 'memberitem', join: 'item' }) || '';
                    let cleanCompName = compName.split(':').pop().trim();
                    
                    if (/^MOD\s*-/i.test(cleanCompName)) return;
                    if (/^Description/i.test(cleanCompName)) return;
                    let compPrefix = cleanCompName.match(/^(\d+)/);
                    if (compPrefix && parseInt(compPrefix[1], 10) >= 900) return;
                    if (ITEMS_TO_EXCLUDE.includes(parseInt(memberItemId))) return;

                    if (uniqueItemIds.indexOf(memberItemId) === -1) uniqueItemIds.push(memberItemId);

                    if (!soMap[soNum].lines[itemKey].componentsMap[memberItemId]) {
                        soMap[soNum].lines[itemKey].componentsMap[memberItemId] = {
                            itemId: memberItemId,
                            reqQty: 0
                        };
                    }
                    soMap[soNum].lines[itemKey].componentsMap[memberItemId].reqQty += (soQty * memberQty);
                }
            });
        });

        for (let so in soMap) {
            for (let k in soMap[so].lines) {
                let line = soMap[so].lines[k];
                if (line.isKit) {
                    line.components = Object.values(line.componentsMap);
                    delete line.componentsMap;
                }
            }
        }

        return { soMap: soMap, itemMap: getItemInventoryMap(uniqueItemIds, selectedLocation) };
    }

    function getItemInventoryMap(uniqueItemIds, selectedLocation) {
        let itemMap = {};
        if (uniqueItemIds.length === 0) return itemMap;

        let itemFilters = [['internalid', 'anyof', uniqueItemIds], 'and', ['isinactive', 'is', 'F']];
        let cols = [search.createColumn({ name: 'itemid' })];

        if (selectedLocation) {
            itemFilters.push('and', ['inventorylocation', 'anyof', selectedLocation]);
            cols.push(search.createColumn({ name: 'locationquantityonhand' }));
        } else {
            cols.push(search.createColumn({ name: 'quantityonhand' }));
        }

        let itemPagedData = search.create({ type: search.Type.ITEM, filters: itemFilters, columns: cols }).runPaged({ pageSize: 1000 });
        
        itemPagedData.pageRanges.forEach(pageRange => {
            let page = itemPagedData.fetch({ index: pageRange.index });
            page.data.forEach(result => {
                let id = result.id;
                let name = (result.getValue('itemid') || '').split(':').pop().trim();
                let onHand = selectedLocation ? parseFloat(result.getValue('locationquantityonhand')) : parseFloat(result.getValue('quantityonhand'));
                
                itemMap[id] = { name: name, onHand: onHand || 0 };
            });
        });
        
        return itemMap;
    }

    function getDetailedData(selectedLocation, startDateStr, endDateStr) {
        let { soMap, itemMap } = extractCoreData(selectedLocation, startDateStr, endDateStr);
        let soArray = [];

        for (let so in soMap) {
            let soData = soMap[so];
            let linesArr = [];

            for (let k in soData.lines) {
                let line = soData.lines[k];

                if (line.isKit) {
                    let populatedComps = [];
                    let kitHasShortage = false;

                    line.components.forEach(comp => {
                        let inv = itemMap[comp.itemId];
                        if (!inv) return;
                        
                        let remaining = inv.onHand - comp.reqQty;
                        let isShort = inv.onHand < comp.reqQty;
                        
                        if (isShort) {
                            kitHasShortage = true;
                            populatedComps.push({
                                itemName: inv.name,
                                orderedQty: comp.reqQty,
                                onHandQty: inv.onHand,
                                remainingStock: remaining
                            });
                        }
                    });
                    
                    if (kitHasShortage) {
                        populatedComps.sort((a, b) => {
                            let weightA = getItemSortWeight(a.itemName);
                            let weightB = getItemSortWeight(b.itemName);
                            if (weightA === weightB) return a.itemName.localeCompare(b.itemName);
                            return weightA - weightB;
                        });
                        
                        line.components = populatedComps;
                        linesArr.push(line);
                    }

                } else {
                    let inv = itemMap[k];
                    if (inv) {
                        let remaining = inv.onHand - line.orderedQty;
                        let isShort = inv.onHand < line.orderedQty;

                        if (isShort) {
                            line.onHandQty = inv.onHand;
                            line.remainingStock = remaining;
                            line.itemName = inv.name; 
                            linesArr.push(line);
                        }
                    }
                }
            }
            
            if (linesArr.length > 0) {
                linesArr.sort((a, b) => {
                    let weightA = getItemSortWeight(a.itemName);
                    let weightB = getItemSortWeight(b.itemName);
                    if (weightA === weightB) return a.itemName.localeCompare(b.itemName);
                    return weightA - weightB;
                });

                soData.linesArr = linesArr;
                soArray.push(soData);
            }
        }

        soArray.sort((a, b) => {
            let parseDate = (dStr) => {
                if (!dStr) return new Date(9999, 11, 31).getTime(); 
                let parts = dStr.split('/');
                if (parts.length === 3) {
                    return new Date(parts[2], parts[1] - 1, parts[0]).getTime(); 
                }
                return new Date(dStr).getTime() || new Date(9999, 11, 31).getTime();
            };
            return parseDate(a.date) - parseDate(b.date);
        });

        return soArray;
    }

    return { onRequest };
});