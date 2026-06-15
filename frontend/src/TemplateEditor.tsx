import { useState,useEffect } from 'react';
import Button from 'react-bootstrap/Button';
import 'bootstrap/dist/css/bootstrap.min.css';
import TextArea from './TextArea';
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

function TemplateEditor() {
    const navigate = useNavigate();

    const [Nikki_data, setNikki_data] = useState('');
    const [Loading, setLoading] = useState(false);

    async function setNikki_data_wrapper(v:string) {
      fetch_with_login(`/template`,
        {
          method: "PUT",
          body:  JSON.stringify({ text:v}),
          headers: {
            'Content-Type': "application/json",
          }
        },navigate)
     
      setNikki_data(v)
    }

    async function Update_template() {
      if(Loading)
        return;
      setLoading(true)

      const result=await fetch_with_login(`/template`,
        {
          method: "GET",
          headers: {
            'Content-Type': "application/json",
          }
        }
        ,navigate)
      
      if (result) {
          setNikki_data(result["text"]);
      }
      setLoading(false)
    }

    useEffect(() => {
        Update_template()

        const id = setInterval(() => {
            Update_template()
        }, 60*60 * 1000)
    }, []);

    return (
        <div id="app" className="m-3">
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

export default TemplateEditor
