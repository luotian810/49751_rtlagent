module TopModule(input tick_i,input arst_ni,input clear_i,input advance_i,
 output reg [2:0] position_o,output reg wrap_o);
 always @(negedge tick_i or negedge arst_ni) begin
   if(!arst_ni) begin position_o<=0;wrap_o<=0;end
   else if(clear_i) begin position_o<=0;wrap_o<=0;end
   else begin
     wrap_o<=0;
     if(advance_i) begin
       if(position_o==6) begin position_o<=0;wrap_o<=1;end
       else position_o<=position_o+1'b1;
     end
   end
 end
endmodule
