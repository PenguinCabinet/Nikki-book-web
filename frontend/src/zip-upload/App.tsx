import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import 'bootstrap/dist/css/bootstrap.min.css';
import { useCookies } from "react-cookie";
import { useNavigate } from 'react-router-dom';
import {fetch_with_login} from "../common/util"


function nikki_zip_upload() {
    const [cookies, setCookie, removeCookie] = useCookies(["token"]);
    const navigate = useNavigate();

    const handleSubmit=(e: React.FormEvent<HTMLFormElement>)=>{

        e.preventDefault();
    
        const formData = new FormData(e.currentTarget); 
        
        fetch_with_login("/nikki-zip",
        {
          method: "POST",
          body:formData,
          headers: {
            'Authorization': 'Bearer '+cookies.token.access_token,
          }
        },navigate,cookies,undefined)
    }

    return (
    <Form onSubmit={handleSubmit}>
      <Form.Text id="passwordHelpBlock" >
        日記のzipでuploadする
      </Form.Text>

      <Form.Control type="file" name="file" />
      <Button type="submit">submit</Button>
    </Form>
    )
}

export default nikki_zip_upload
