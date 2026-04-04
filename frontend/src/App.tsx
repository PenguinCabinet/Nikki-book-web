import { useState } from 'react';
import Button from 'react-bootstrap/Button';
import Nav from 'react-bootstrap/Nav';
import Tabs from 'react-bootstrap/Tabs';
import Tab from 'react-bootstrap/Tab';
import FloatingLabel from 'react-bootstrap/FloatingLabel';
import Form from 'react-bootstrap/Form';
import 'bootstrap/dist/css/bootstrap.min.css';
import TextArea from './TextArea';
import { useCookies } from "react-cookie";
import {fetch_with_login} from "./common/util"
import { useNavigate } from 'react-router-dom';

function DatetoString(v:any) {
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
    const [cookies, setCookie, removeCookie] = useCookies(["token"]);

    const navigate = useNavigate();

    const [Nikki_data, setNikki_data] = useState('');
    const [Loading, setLoading] = useState(false);

    const [date, setDate] = useState(new Date());


    async function setNikki_data_wrapper(v:string) {
      fetch_with_login(`/nikki/${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`,'PUT',{ text:v},navigate,cookies)
     
      setNikki_data(v)
    }

    async function Nikki_move_diff(m:number, d:number) {
      setLoading(true)
      let new_date = new Date(date.getTime())
      new_date.setMonth(date.getMonth() + m)
      new_date.setDate(date.getDate() + d)
      setDate(new_date)

      const result=await fetch_with_login(`/nikki/${new_date.getFullYear()}-${new_date.getMonth() + 1}-${new_date.getDate()}`,'GET',null,navigate,cookies)
      
      setNikki_data(result["text"]);
      setLoading(false)
    }


    return (
        <div id="app" className="m-3">
            <div className="my-3">
                <Button
                    className='mx-2'
                    id="Nikki_move_prev_month"
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff(-1, 0) }}>
                    ←←
                </Button>
                <Button
                    id="Nikki_move_prev"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff(0, -1) }}>
                    ←
                </Button>
                <Button
                    id="Nikki_move_next"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff(0, 1) }}>
                    →
                </Button>
                <Button
                    id="Nikki_move_next_month"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { Nikki_move_diff(1, 0) }}>
                    →→
                </Button>
                <Button
                    id="Nikki_move_today"
                    className='mx-2'
                    variant="outline-primary"
                    onClick={() => { setDate(new Date()) }}
                >
                    Today
                </Button>
            </div>
            <h1>{DatetoString(date)}</h1>
            <div>
                <TextArea
                    data={Nikki_data}
                    setData={setNikki_data_wrapper}
                    Do_not_edit_flag={Loading}
                />
            </div>
        </div>
    )
}

export default Nikki
