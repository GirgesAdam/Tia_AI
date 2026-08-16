const days=["الإثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"];
export function SetupHoursFields({defaultStart="10:00",defaultEnd="22:00"}:{defaultStart?:string;defaultEnd?:string}){
  return <div className="space-y-2">{days.map((day,i)=><div key={day} className="grid grid-cols-[90px_1fr_1fr] items-center gap-2 rounded-xl bg-[var(--surface-2)] p-2">
    <label className="flex items-center gap-2 text-xs font-bold"><input type="checkbox" name={`day_${i}`} defaultChecked={i!==4}/>{day}</label>
    <input type="time" name={`start_${i}`} defaultValue={defaultStart} className="rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-xs"/>
    <input type="time" name={`end_${i}`} defaultValue={defaultEnd} className="rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-xs"/>
  </div>)}</div>
}
