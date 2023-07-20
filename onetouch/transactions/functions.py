from fpdf import FPDF


def uplatnice_gen(data_list, qr_code_images):
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            self.add_font('DejaVuSansCondensed', '', './onetouch/static/fonts/DejaVuSansCondensed.ttf', uni=True)
            self.add_font('DejaVuSansCondensed', 'B', './onetouch/static/fonts/DejaVuSansCondensed-Bold.ttf', uni=True)
    pdf = PDF()
    # pdf.add_page()
    counter = 1
    for i, uplatnica in enumerate(data_list):
        print(f'{uplatnica=}')
        if counter % 3 == 1:
            pdf.add_page()
            y = 0
            y_qr = 50
            pdf.line(210/2, 10, 210/2, 237/3)
        elif counter % 3 == 2:
            y = 99
            y_qr = 149
            pdf.line(210/2, 110, 210/2, 99+237/3)
        elif counter % 3 == 0:
            y = 198
            y_qr = 248
            pdf.line(210/2, 210, 210/2, 198+237/3)
        pdf.set_font('DejaVuSansCondensed', 'B', 16)
        pdf.set_y(y_qr)
        pdf.set_x(175)
        pdf.image(f'onetouch/static/payment_slips/qr_code/{qr_code_images[i]}' , w=25)
        pdf.set_y(y+8)
        pdf.cell(0,8, f"NALOG ZA UPLATU", new_y='NEXT', new_x='LMARGIN', align='R', border=0)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        pdf.cell(95,4, f"Uplatilac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(90,4, f'''{uplatnica['uplatilac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(95,4, f"Svrha uplate", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(90,4, f'''{uplatnica['svrha_uplate']}\r\n{''}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(95,4, f"Primalac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(90,4, f'''{uplatnica['primalac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(95,1, f"", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.set_font('DejaVuSansCondensed', '', 7)
        pdf.cell(50,4, f"Pečat i potpis uplatioca", new_y='NEXT', new_x='LMARGIN', align='L', border='T')
        pdf.cell(95,1, f"", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.set_x(50)
        pdf.cell(50,4, f"Mesto i datum prijema", new_y='LAST', align='L', border='T')
        pdf.set_x(110)
        pdf.cell(40,5, f"Datum valute", align='L', border='T')
        pdf.set_y(y + 15)
        pdf.set_x(110)
        pdf.set_font('DejaVuSansCondensed', '', 8)
        pdf.multi_cell(13,3, f"Šifra plaćanja", new_y='LAST', align='L', border=0)
        pdf.multi_cell(7,3, f"", new_y='LAST', align='L', border=0)
        pdf.multi_cell(13,3, f"Valuta", new_y='LAST', align='L', border=0)
        pdf.multi_cell(10,3, f"", new_y='LAST', align='L', border=0)
        pdf.multi_cell(13,3, f"Iznos", new_y='NEXT', align='L', border=0)
        pdf.set_x(110)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        pdf.multi_cell(13,6, f"{uplatnica['sifra_placanja']}", new_y='LAST', align='L', border=1)
        pdf.multi_cell(7,6, f"", new_y='LAST', align='L', border=0)
        pdf.multi_cell(13,6, f"RSD", new_y='LAST', align='L', border=1)
        pdf.multi_cell(10,6, f"", new_y='LAST', align='L', border=0)
        pdf.multi_cell(47,6, f"{uplatnica['iznos']}", new_y='NEXT', align='L', border=1)
        pdf.set_x(110)
        pdf.set_font('DejaVuSansCondensed', '', 8)
        pdf.multi_cell(90,5, f"Račun primaoca", new_y='NEXT', align='L', border=0)
        pdf.set_x(110)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        pdf.multi_cell(90,6, f"{uplatnica['racun_primaoca']}", new_y='NEXT', align='L', border=1)
        pdf.set_x(110)
        pdf.set_font('DejaVuSansCondensed', '', 8)
        pdf.multi_cell(90,5, f"Model i poziv na broj (odobrenje)", new_y='NEXT', align='L', border=0)
        pdf.set_x(110)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        pdf.multi_cell(10,6, f"{uplatnica['model']}", new_y='LAST', align='L', border=1)
        pdf.multi_cell(10,6, f"", new_y='LAST', align='L', border=0)
        pdf.multi_cell(70,6, f"{uplatnica['poziv_na_broj']}", new_y='LAST', align='L', border=1)
        
        pdf.line(10, 99, 200, 99)
        pdf.line(10, 198, 200, 198)
        counter += 1
    path = "onetouch/static/payment_slips/"
    file_name = f'uplatnice.pdf'
    pdf.output(path + file_name)
    return file_name