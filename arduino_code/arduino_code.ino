/*
 * MUX DISPLAY v0.1
 * 
 * The microcontroller code to control PortB output,
 * sample analog singnals,
 * accept serial commands to change variables,
 * output data over serial for the desktop program,
 * etc.
 * 
 * Is designed to be run with the desktop program
 * controlling all serial commands, but can also
 * be used to configure the mux with just a standard
 * serial connection.
 * 
 * Author:  - David Vitale
 * Date:    - 2017-12-07
*/

#define BUFFER_SIZE 15
#define ERROR -1
#define True 1
#define False 0

const char *help_text = "MUX CONTROLLER v0.1\r\n"
                        "'h'->print this help prompt\r\n"
                        "'v'->print current variables\r\n"
                        "'l'->set lower bound\r\n"
                        "'u'->set upper bound\r\n"
                        "'p'->set cycling period\r\n"
                        "'d'->toggle data streaming\r\n"
                        "'c'->start cycling mode\r\n"
                        "'s'->start single select mode\r\n";

boolean data_streaming = true;
unsigned int lower_bound = 0;
unsigned int upper_bound = 15;
unsigned int cycling_period = 1562; //100 ms
//1 second = 15624

boolean is_cycling = true;
byte counter = 0;

// the setup function runs once when you press reset or power the board
void setup() {
  // initialize digital pin LED_BUILTIN as an output.
  pinMode(LED_BUILTIN, OUTPUT);
  DDRB = 0xFF; //all as outputs

  //TIMER INTERRUPT SETUP
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1  = 0; //initialize counter value
  OCR1A = cycling_period; //set the cycling_period to the timer compare
  TCCR1B |= (1 << WGM12); //CTC mode
  TCCR1B |= (1 << CS12) | (1 << CS10); //1024 divider
  TIMSK1 |= (1 << OCIE1A);  //enable compare interrupt

  Serial.begin(115200);
  Serial.println(help_text);
  delay(100);
}

// the loop function runs over and over again forever
void loop() {
  check_for_input();
  delay(1); //1000Hz(ish) Sampling Rate
  if(data_streaming)
    Serial.println(analogRead(0));
}

void check_for_input(){
        if (Serial.available() > 0) {
                int num;
                // read the incoming byte:
                char menu_option = Serial.read();
                switch(menu_option){

                case 'h':
                  Serial.println(help_text);
                  break;

                case 'v':
                  print_variables();
                  break; 

                case 'l':
                  num = query_user_for_number(0,254);
                  if(num != ERROR){
                    lower_bound = num;
                    print_variables();
                  }
                  break;

                case 'u':
                  num = query_user_for_number(1,255);
                  if(num != ERROR){
                    upper_bound = num;
                    print_variables();
                  }
                  break;

                case 'p':
                  num = query_user_for_number(1,0xFFFE);
                  if(num != ERROR){
                    cycling_period = num;
                    TCNT1  = 0;
                    OCR1A = cycling_period;
                    print_variables();
                  }
                  break;

                case 'd':
                  data_streaming ^= 1;  //toggle data streaming
                  print_variables();
                  break;

                case 'c':
                  is_cycling = True;
                  counter = lower_bound;
                  // enable timer compare interrupt
                  TIMSK1 |= (1 << OCIE1A);
                  break;

                case 's':
                  is_cycling = False;
                  // disable timer compare interrupt
                  TIMSK1 &= ~(1 << OCIE1A);
                  num = query_user_for_number(0, 255);
                  if(num != ERROR){
                    PORTB = num;
                  }
                  break;

                default:
                  Serial.println("Not recognized");
                }
        }
}

void print_variables(){
  Serial.print("lower_bound->");
  Serial.println(lower_bound, DEC);
  Serial.print("upper_bound->");
  Serial.println(upper_bound, DEC);
  Serial.print("cycling_period->");
  Serial.println(cycling_period, DEC);
  Serial.print("data_streaming->");
  Serial.println(data_streaming, DEC);
  Serial.print("is_cycling->");
  Serial.println(is_cycling, DEC);
}

int query_user_for_number(unsigned int lower_bound, unsigned int upper_bound){
  /*Initialize variables and alert user of entering a number*/
  int num = 0;
  Serial.println("Enter #. 'q' when done.");
  delay(100); //delay to allow string to print
  int i = 0;
  char tmp = '0';
  char buff[BUFFER_SIZE];

  /*after user presses 'q' to stop, convert the inputted string into a num*/
  while((tmp != 'q') && (i < (BUFFER_SIZE - 2))){
    if (Serial.available() > 0) {
      buff[i] = tmp;
      i++;
      tmp = Serial.read();
    }
  }
  buff[i]='\0';
  num = atoi(buff);

  /*check for bounds then return the number*/
  if(num < lower_bound || num > upper_bound){
    Serial.println("ERR: OUT OF RANGE");
    Serial.print("lower_bound->");
    Serial.println(lower_bound, DEC);
    Serial.print("upper_bound->");
    Serial.println(upper_bound, DEC);
    return ERROR;
  }
  Serial.println("DONE");
  return num;
}

ISR(TIMER1_COMPA_vect){
    if(counter++ >= upper_bound){
      counter = lower_bound;
    }
    PORTB = counter;
}


