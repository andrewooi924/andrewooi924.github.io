// Reprice today's quantities across observed dates. This is not a transaction ledger.
export function collectionHistory(items, histories) {
  const dates=new Map();
  for(const item of items){
    const quantity=Number.isInteger(item.quantity)&&item.quantity>0?item.quantity:1;
    for(const [date,price] of histories[item.id]||[]){
      if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(price)||price<0)continue;
      const point=dates.get(date)||{date,value:0,priced:0};
      point.value+=price*quantity;point.priced++;dates.set(date,point);
    }
  }
  return [...dates.values()].sort((a,b)=>a.date.localeCompare(b.date)).map(p=>({...p,complete:p.priced===items.length}));
}
