import { useState } from 'react';
import Button from 'react-bootstrap/Button';
import 'bootstrap/dist/css/bootstrap.min.css';
import TextArea from './TextArea';
import { useCollaborativeText } from './common/useCollaborativeText';

function DatetoString(v:Date) {
    const day_string_arr = [
        "(日)",
        "(月)",
        "(火)",
        "(水)",
        "(木)",
        "(金)",
        "(土)",
    ];
    return `${v.getFullYear()}年${v.getMonth() + 1}月${v.getDate()}日 ${day_string_arr[v.getDay()]}`
}

function Nikki() {
    const [date, setDate] = useState(new Date());
    const sync = useCollaborativeText(`/nikki/${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`);

    async function Nikki_move_diff(diff_year_func:(current:number)=>number, diff_month_func:(current:number)=>number, diff_date_func:(current:number)=>number) {
      const new_date = new Date(date.getTime())

      new_date.setFullYear(diff_year_func(date.getFullYear()))

      new_date.setDate(1)
      new_date.setMonth(diff_month_func(date.getMonth()))
      const last_day_in_month = new Date(new_date.getFullYear(), new_date.getMonth() + 1, 0).getDate();
      new_date.setDate(
        Math.min(
            date.getDate(),
            last_day_in_month,
        )
      )

      new_date.setDate(diff_date_func(new_date.getDate()))

      setDate(new_date)

    }

    return (
        <div id="app" className="m-3">
            <div className="my-3">
                <Button
                    className='mx-2'
                    id="Nikki_move_prev_month"
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff((c)=>c,(c)=>c-1, (c)=>c) }}>
                    ←←
                </Button>
                <Button
                    id="Nikki_move_prev"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff((c)=>c,(c)=>c,(c)=>c-1) }}>
                    ←
                </Button>
                <Button
                    id="Nikki_move_next"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff((c)=>c,(c)=>c, (c)=>c+1) }}>
                    →
                </Button>
                <Button
                    id="Nikki_move_next_month"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff((c)=>c,(c)=>c+1, (c)=>c) }}>
                    →→
                </Button>
                <Button
                    id="Nikki_move_today"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff(
                        (c)=>(new Date()).getFullYear(),
                        (c)=>(new Date()).getMonth(), 
                        (c)=>(new Date()).getDate()) 
                    }}
                >
                    Today
                </Button>
            </div>
            <h1>{DatetoString(date)}</h1>
            <div>
                <TextArea
                    data={sync.text}
                    setData={sync.setText}
                    Do_not_edit_flag={sync.loading}
                    setComposing={sync.setComposing}
                />
            </div>
        </div>
    )
}

export default Nikki
