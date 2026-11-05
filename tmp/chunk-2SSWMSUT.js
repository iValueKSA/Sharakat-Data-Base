function S(n,e){if(!n)return"";let l=(g,i)=>(e?g||i:i||g)||"",r=n.showAsUpcoming?e?"\u0642\u0627\u062F\u0645":"Upcoming":l(n.displayStageParentNameAr,n.displayStageParentNameEn),s=l(n.displayStageSubNameAr,n.displayStageSubNameEn),t=r.trim(),a=s.trim();return t&&a&&t!==a?`${t} \xBB ${a}`:a||t}export{S as a};

